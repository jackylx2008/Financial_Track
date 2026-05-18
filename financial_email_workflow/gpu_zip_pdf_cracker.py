from __future__ import annotations

import argparse
import struct
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = Path("raw_data/financial_email/attachment_inventory.json")
DEFAULT_MANIFEST = Path(
    "raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json"
)
DEFAULT_OUTPUT = Path("raw_data/financial_email/cracked_attachment_passwords.env.snippet")
DEFAULT_MASKS = ["?d?d?d?d?d?d", "?d?d?d?d"]
DEFAULT_ZIP_MODES = [13600, 17225, 17220, 17210, 17200]
DEFAULT_PDF_MODES = [10700, 10600, 10500, 10400]
DEFAULT_PASSWORD_ENV = Path("financial_attachment_passwords.env")


@dataclass(frozen=True)
class CrackTarget:
    path: Path
    kind: str
    filename: str
    bank_key: str
    subject: str
    sent_at: str
    status: str


@dataclass(frozen=True)
class CrackResult:
    target: CrackTarget
    status: str
    reason: str
    password: str = ""
    mode: int | None = None
    mask: str = ""
    hash_file: Path | None = None


def main() -> int:
    configure_console_encoding()
    args = parse_args()
    apply_config_defaults(args)
    if args.check_tools:
        print_tool_check(args)
        return 0
    targets = load_targets(args)
    if args.zip_aes_only:
        targets = [target for target in targets if target.kind == "zip" and is_aes_zip(target.path)]
    if not targets:
        print("未找到需要破解的 ZIP/PDF 邮件附件。")
        return 0
    targets, skipped_saved_count = skip_saved_targets(targets, args.password_env)
    if not targets:
        print("没有需要破解的附件。")
        return 0
    if args.list_targets:
        print_targets(targets)
        return 0

    hashcat = resolve_executable(args.hashcat)
    if not hashcat:
        print("未找到 hashcat，请安装 hashcat 或通过 --hashcat 指定完整路径。")
        return 2

    zip2john = (
        resolve_executable(args.zip2john)
        if args.zip2john
        else find_john_tool("zip2john")
    )
    pdf2john = (
        resolve_executable(args.pdf2john)
        if args.pdf2john
        else find_john_tool("pdf2john")
    )

    print(f"待破解附件数：{len(targets)}")
    print(f"输出 env 片段：{args.output}")
    print("控制台默认不输出真实密码；需要显示时使用 --show-passwords。")

    results: list[CrackResult] = []
    with tempfile.TemporaryDirectory(prefix="financial_attachment_hashcat_") as temp_dir:
        for index, target in enumerate(targets, start=1):
            print(f"[{index}/{len(targets)}] {target.kind.upper()} {target.path}")
            result = crack_target(
                target=target,
                temp_dir=Path(temp_dir),
                hashcat=hashcat,
                zip2john=zip2john,
                pdf2john=pdf2john,
                hashcat_extra_args=args.hashcat_extra_arg,
                masks=args.mask,
                wordlists=args.wordlist,
                candidate_profile=args.candidate_profile,
                password_env=args.password_env,
                zip_modes=args.zip_mode,
                pdf_modes=args.pdf_mode,
                workload=args.workload,
                keep_hashes=args.keep_hashes,
            )
            results.append(result)
            print(format_result(result, show_passwords=args.show_passwords))

    persisted_count = persist_cracked_passwords(results, args.password_env)
    write_password_snippet(results, args.output)
    print_summary(results, args.output, args.password_env, persisted_count)
    return (
        0 if all(item.status in {"cracked", "not_cracked"} for item in results) else 1
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use hashcat to crack project financial email ZIP/PDF attachment passwords."
    )
    parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="项目配置文件路径。")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="附件提取阶段输出清单。",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
        help="附件准备阶段输出清单。",
    )
    parser.add_argument(
        "--attachment",
        action="append",
        type=Path,
        help="直接指定一个 ZIP/PDF 附件，可重复传入。",
    )
    parser.add_argument(
        "--target",
        choices=["failed", "encrypted", "all"],
        default="failed",
        help="failed 优先读取提取失败清单；encrypted 读取清单中的加密附件；all 处理所有 ZIP/PDF。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="破解成功密码的本地 env 片段输出路径。",
    )
    parser.add_argument(
        "--mask",
        action="append",
        default=[],
        help="hashcat 掩码，可重复传入。默认尝试 6 位和 4 位数字。",
    )
    parser.add_argument(
        "--wordlist",
        action="append",
        type=Path,
        default=[],
        help="密码字典文件，可重复传入。",
    )
    parser.add_argument(
        "--candidate-profile",
        choices=["auto", "none"],
        default="auto",
        help="auto 会先尝试项目 env 密码和附件名/日期派生候选。",
    )
    parser.add_argument(
        "--password-env",
        type=Path,
        default=DEFAULT_PASSWORD_ENV,
        help="项目附件密码 env 文件，用于优先尝试已配置候选。",
    )
    parser.add_argument(
        "--zip-mode",
        action="append",
        type=int,
        default=[],
        help="ZIP hashcat mode，可重复传入。",
    )
    parser.add_argument(
        "--pdf-mode",
        action="append",
        type=int,
        default=[],
        help="PDF hashcat mode，可重复传入。",
    )
    parser.add_argument("--hashcat", help="hashcat 可执行文件路径或命令名。")
    parser.add_argument(
        "--hashcat-extra-arg",
        action="append",
        default=[],
        help="额外传给 hashcat 的参数，可重复传入。",
    )
    parser.add_argument("--zip2john", help="zip2john 可执行文件路径或命令名。")
    parser.add_argument("--pdf2john", help="pdf2john 可执行文件路径或命令名。")
    parser.add_argument("--workload", default="3", help="hashcat -w 工作负载，默认 3。")
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="只列出会处理的附件，不调用 hashcat。",
    )
    parser.add_argument(
        "--check-tools",
        action="store_true",
        help="只检查配置中的 hashcat/zip2john/pdf2john 路径，不调用破解。",
    )
    parser.add_argument(
        "--zip-aes-only",
        action="store_true",
        help="只处理 WinZip AES 加密 ZIP 附件。",
    )
    parser.add_argument(
        "--keep-hashes",
        action="store_true",
        help="保留提取出的 hash 文件，便于手工复跑。",
    )
    parser.add_argument(
        "--show-passwords", action="store_true", help="在控制台显示破解出的真实密码。"
    )
    args = parser.parse_args()
    args.mask = args.mask or DEFAULT_MASKS
    args.zip_mode = args.zip_mode or DEFAULT_ZIP_MODES
    args.pdf_mode = args.pdf_mode or DEFAULT_PDF_MODES
    return args


def apply_config_defaults(args: argparse.Namespace) -> None:
    config = load_project_config(args.config)
    section = config.get("financial_attachment_cracker", {})
    if not isinstance(section, dict):
        section = {}

    args.manifest = resolve_runtime_path(args.manifest)
    args.inventory = resolve_runtime_path(args.inventory)
    args.output = resolve_runtime_path(args.output)
    args.password_env = resolve_runtime_path(args.password_env)
    args.wordlist = [resolve_runtime_path(path) for path in args.wordlist]
    if args.attachment:
        args.attachment = [resolve_runtime_path(path) for path in args.attachment]

    args.hashcat = args.hashcat or resolve_config_path(section.get("hashcat_path")) or "hashcat"
    args.zip2john = args.zip2john or resolve_config_path(section.get("zip2john_path"))
    args.pdf2john = args.pdf2john or resolve_config_path(section.get("pdf2john_path"))
    if not args.hashcat_extra_arg:
        extra_args = section.get("hashcat_extra_args", [])
        if isinstance(extra_args, str):
            args.hashcat_extra_arg = [extra_args] if extra_args else []
        elif isinstance(extra_args, list):
            args.hashcat_extra_arg = [str(item) for item in extra_args if str(item)]


def load_project_config(config_path: Path) -> dict[str, Any]:
    src_path = PROJECT_ROOT / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    try:
        from localai.modules.config_loader import load_config
    except Exception:
        return {}

    resolved_config = config_path if config_path.is_absolute() else PROJECT_ROOT / config_path
    if not resolved_config.exists():
        return {}
    try:
        data = load_config(resolved_config)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def resolve_config_path(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return str(path)
    return str((PROJECT_ROOT / path).resolve())


def resolve_runtime_path(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded
    return (PROJECT_ROOT / expanded).resolve()


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def load_targets(args: argparse.Namespace) -> list[CrackTarget]:
    if args.attachment:
        return [target_from_path(path) for path in args.attachment]

    targets: list[CrackTarget] = []
    if args.target == "failed" and args.manifest.exists():
        targets = [
            target_from_item(item)
            for item in read_json_list(args.manifest)
            if item.get("status") == "password_failed"
            and extension_kind(Path(str(item.get("path", "")))) in {"zip", "pdf"}
        ]
    if targets:
        return dedupe_targets(targets)

    if args.inventory.exists():
        items = read_json_list(args.inventory)
        for item in items:
            path = Path(str(item.get("path", "")))
            kind = extension_kind(path)
            if kind not in {"zip", "pdf"}:
                continue
            encrypted_status = str(item.get("encrypted_status", ""))
            if args.target == "all" or encrypted_status in {
                "encrypted",
                "maybe_encrypted",
            }:
                targets.append(target_from_item(item))
    return dedupe_targets(targets)


def skip_saved_targets(
    targets: list[CrackTarget], password_env: Path
) -> tuple[list[CrackTarget], int]:
    saved_filenames = saved_attachment_filenames(password_env)
    if not saved_filenames:
        return targets, 0

    kept: list[CrackTarget] = []
    skipped = 0
    for target in targets:
        if target.kind in {"zip", "pdf"} and target.filename.lower() in saved_filenames:
            skipped += 1
            continue
        kept.append(target)
    return kept, skipped


def saved_attachment_filenames(password_env: Path) -> set[str]:
    values = read_env_assignments(password_env)
    by_filename = parse_json_object(
        values.get("FINANCIAL_ATTACHMENT_PASSWORD_BY_FILENAME_JSON", "{}")
    )
    return {
        filename.lower()
        for filename, password in by_filename.items()
        if Path(str(filename)).suffix.lower() in {".zip", ".pdf"}
        and normalize_password_value(password)
    }


def crack_target(
    target: CrackTarget,
    temp_dir: Path,
    hashcat: Path,
    zip2john: Path | None,
    pdf2john: Path | None,
    hashcat_extra_args: list[str],
    masks: list[str],
    wordlists: list[Path],
    candidate_profile: str,
    password_env: Path,
    zip_modes: list[int],
    pdf_modes: list[int],
    workload: str,
    keep_hashes: bool,
) -> CrackResult:
    if not target.path.exists():
        return CrackResult(target=target, status="error", reason="附件文件不存在")

    candidate_passwords = build_candidate_passwords(target, password_env) if candidate_profile == "auto" else []
    for password in candidate_passwords:
        if verify_password(target, password):
            return CrackResult(
                target=target,
                status="cracked",
                reason="已通过候选密码验证",
                password=password,
                mode=None,
                mask="candidate",
            )

    direct_zip_result = crack_traditional_zip_numeric_masks(target, masks)
    if direct_zip_result is not None:
        password, mask = direct_zip_result
        return CrackResult(
            target=target,
            status="cracked",
            reason="已通过 ZIP 直接数字掩码验证",
            password=password,
            mode=None,
            mask=mask,
        )

    john_tool = zip2john if target.kind == "zip" else pdf2john
    if not john_tool:
        return CrackResult(
            target=target,
            status="error",
            reason=f"未找到 {target.kind}2john，请用 --{target.kind}2john 指定",
        )

    try:
        hash_string = extract_hash(john_tool, target.path, target.kind)
    except RuntimeError as exc:
        direct_pdf_result = crack_pdf_numeric_masks(target, masks)
        if direct_pdf_result is not None:
            password, mask = direct_pdf_result
            return CrackResult(
                target=target,
                status="cracked",
                reason="已通过 PDF 直接数字掩码验证",
                password=password,
                mode=None,
                mask=mask,
            )
        return CrackResult(target=target, status="error", reason=str(exc))

    hash_file = temp_dir / f"{safe_stem(target.path)}.{target.kind}.hash"
    hash_file.write_text(hash_string + "\n", encoding="utf-8")

    modes = compatible_modes(hash_string, target.kind, zip_modes, pdf_modes)
    generated_wordlist = write_candidate_wordlist(temp_dir, target, candidate_passwords)
    effective_wordlists = [path for path in [generated_wordlist, *wordlists] if path and path.exists()]
    for mode in modes:
        for wordlist in effective_wordlists:
            run_hashcat_wordlist(hashcat=hashcat, hash_file=hash_file, mode=mode, wordlist=wordlist, workload=workload, extra_args=hashcat_extra_args)
            password = show_hashcat_password(hashcat=hashcat, hash_string=hash_string, hash_file=hash_file, mode=mode, extra_args=hashcat_extra_args)
            if password is not None and verify_password(target, password):
                kept_hash = keep_hash(hash_file, target) if keep_hashes else None
                return CrackResult(
                    target=target,
                    status="cracked",
                    reason="已破解",
                    password=password,
                    mode=mode,
                    mask=f"wordlist:{wordlist.name}",
                    hash_file=kept_hash,
                )

    for mode in modes:
        for mask in masks:
            run_hashcat(
                hashcat=hashcat,
                hash_file=hash_file,
                mode=mode,
                mask=mask,
                workload=workload,
                extra_args=hashcat_extra_args,
            )
            password = show_hashcat_password(hashcat=hashcat, hash_string=hash_string, hash_file=hash_file, mode=mode, extra_args=hashcat_extra_args)
            if password is not None and verify_password(target, password):
                kept_hash = keep_hash(hash_file, target) if keep_hashes else None
                return CrackResult(
                    target=target,
                    status="cracked",
                    reason="已破解",
                    password=password,
                    mode=mode,
                    mask=mask,
                    hash_file=kept_hash,
                )

    kept_hash = keep_hash(hash_file, target) if keep_hashes else None
    return CrackResult(
        target=target,
        status="not_cracked",
        reason="当前 mode/mask 未破解",
        hash_file=kept_hash,
    )


def crack_traditional_zip_numeric_masks(target: CrackTarget, masks: list[str]) -> tuple[str, str] | None:
    if target.kind != "zip" or is_aes_zip(target.path):
        return None

    numeric_masks = [
        (mask, length)
        for mask in masks
        if (length := numeric_digit_mask_length(mask)) is not None and length <= 6
    ]
    if not numeric_masks:
        return None

    try:
        with zipfile.ZipFile(target.path) as archive:
            first_file = next((info for info in archive.infolist() if not info.is_dir()), None)
            if first_file is None:
                return "", numeric_masks[0][0]
            for mask, length in numeric_masks:
                for number in range(10**length):
                    password = f"{number:0{length}d}"
                    if zip_member_opens_with_password(archive, first_file, password):
                        return password, mask
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def crack_pdf_numeric_masks(target: CrackTarget, masks: list[str]) -> tuple[str, str] | None:
    if target.kind != "pdf":
        return None

    numeric_masks = [
        (mask, length)
        for mask in masks
        if (length := numeric_digit_mask_length(mask)) is not None and length <= 6
    ]
    if not numeric_masks:
        return None

    for mask, length in numeric_masks:
        for number in range(10**length):
            password = f"{number:0{length}d}"
            if verify_pdf_password(target.path, password):
                return password, mask
    return None


def numeric_digit_mask_length(mask: str) -> int | None:
    if not mask or len(mask) % 2:
        return None
    parts = [mask[index : index + 2] for index in range(0, len(mask), 2)]
    if all(part == "?d" for part in parts):
        return len(parts)
    return None


def zip_member_opens_with_password(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, password: str
) -> bool:
    try:
        with archive.open(info, pwd=password.encode("ascii")) as source:
            source.read(1)
            source.read()
        return True
    except Exception:
        return False


def compatible_modes(hash_string: str, kind: str, zip_modes: list[int], pdf_modes: list[int]) -> list[int]:
    if kind == "pdf":
        return pdf_modes
    if hash_string.startswith("$zip2$"):
        return [mode for mode in zip_modes if mode == 13600] or [13600]
    if hash_string.startswith(("$pkzip2$", "$pkzip$")):
        pkzip_modes = {17225, 17220, 17210, 17200}
        return [mode for mode in zip_modes if mode in pkzip_modes] or [17225, 17220, 17210, 17200]
    return zip_modes


def build_candidate_passwords(target: CrackTarget, password_env: Path) -> list[str]:
    candidates: list[str] = []
    candidates.extend(resolve_configured_passwords(target, password_env))
    candidates.extend(derive_password_candidates(target))
    return unique_nonempty(candidates)


def resolve_configured_passwords(target: CrackTarget, password_env: Path) -> list[str]:
    if not password_env.exists():
        return []
    src_path = PROJECT_ROOT / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    try:
        from localai.modules.financial_attachment_passwords import AttachmentPasswordStore
    except Exception:
        return []
    try:
        store = AttachmentPasswordStore.from_env_file(password_env)
        match = store.resolve(bank_key=target.bank_key, attachment_path=target.path)
    except Exception:
        return []
    return match.passwords if match else []


def derive_password_candidates(target: CrackTarget) -> list[str]:
    text = " ".join([target.filename, target.subject, target.sent_at, str(target.path)])
    dates = re.findall(r"(20\d{6})", text)
    six_digit_groups = re.findall(r"(?<!\d)(\d{6})(?!\d)", text)
    long_digit_groups = re.findall(r"\d{8,24}", text)

    candidates: list[str] = []
    candidates.extend(dates)
    candidates.extend(six_digit_groups)
    for value in long_digit_groups:
        candidates.extend([value, value[-4:], value[-6:], value[-8:]])
    for date in dates:
        candidates.extend([date[2:], date[4:], date[-4:]])
    return candidates


def unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def write_candidate_wordlist(temp_dir: Path, target: CrackTarget, candidates: list[str]) -> Path | None:
    if not candidates:
        return None
    wordlist = temp_dir / f"{safe_stem(target.path)}.candidates.txt"
    wordlist.write_text("\n".join(candidates) + "\n", encoding="utf-8")
    return wordlist


def extract_hash(john_tool: Path, attachment: Path, kind: str) -> str:
    completed = subprocess.run(
        executable_command(john_tool) + [str(attachment)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
    hash_value = extract_john_hash_from_output(output, kind)
    if hash_value:
        return hash_value

    if completed.returncode != 0:
        if kind == "zip" and is_aes_zip(attachment):
            aes_hash = extract_winzip_aes_hash(attachment)
            if aes_hash:
                return aes_hash
        reason = f"{john_tool.name} 执行失败，退出码 {completed.returncode}"
        if kind == "zip" and is_aes_zip(attachment):
            reason += "；该 ZIP 使用 AES 加密，当前 Windows zip2john.exe 未能提取 hash"
        raise RuntimeError(reason)
    if kind == "zip" and is_aes_zip(attachment):
        aes_hash = extract_winzip_aes_hash(attachment)
        if aes_hash:
            return aes_hash
    raise RuntimeError(f"未能从 {john_tool.name} 输出中提取 {kind.upper()} hash")


def extract_winzip_aes_hash(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.compress_type != 99:
                continue
            strength = zip_aes_strength(info.extra)
            if strength not in {1, 2, 3}:
                continue
            salt_len = {1: 8, 2: 12, 3: 16}[strength]
            with path.open("rb") as file:
                file.seek(info.header_offset)
                local_header = file.read(30)
                if len(local_header) != 30 or local_header[:4] != b"PK\x03\x04":
                    continue
                filename_len, extra_len = struct.unpack_from("<HH", local_header, 26)
                file.seek(filename_len + extra_len, 1)
                payload = file.read(info.compress_size)
            min_len = salt_len + 2 + 10
            if len(payload) < min_len:
                continue
            salt = payload[:salt_len]
            checksum = payload[salt_len : salt_len + 2]
            encrypted_content = payload[salt_len + 2 : -10]
            auth_code = payload[-10:]
            if not encrypted_content:
                continue
            return (
                f"$zip2$*0*{strength}*0*"
                f"{salt.hex()}*{checksum.hex()}*{len(encrypted_content):x}*"
                f"{encrypted_content.hex()}*{auth_code.hex()}*$/zip2$"
            )
    return ""


def zip_aes_strength(extra: bytes) -> int | None:
    offset = 0
    while offset + 4 <= len(extra):
        header_id, data_size = struct.unpack_from("<HH", extra, offset)
        offset += 4
        data = extra[offset : offset + data_size]
        offset += data_size
        if header_id == 0x9901 and len(data) >= 7:
            return data[4]
    return None


def extract_john_hash_from_output(output: str, kind: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if kind == "pdf":
            hash_value = extract_marker_hash(stripped, "$pdf$")
            if hash_value:
                return hash_value
        if kind == "zip":
            for start_marker, end_marker in [
                ("$zip2$", "$/zip2$"),
                ("$pkzip2$", "$/pkzip2$"),
                ("$pkzip$", "$/pkzip$"),
            ]:
                hash_value = extract_marker_hash(stripped, start_marker, end_marker)
                if hash_value:
                    return hash_value
    return ""


def extract_marker_hash(line: str, start_marker: str, end_marker: str | None = None) -> str:
    start = line.find(start_marker)
    if start < 0:
        return ""
    if end_marker:
        end = line.find(end_marker, start)
        if end < 0:
            return ""
        return line[start : end + len(end_marker)]
    return line[start:].split()[0]


def is_aes_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return any(info.compress_type == 99 for info in archive.infolist())
    except (OSError, zipfile.BadZipFile):
        return False


def run_hashcat(
    hashcat: Path, hash_file: Path, mode: int, mask: str, workload: str, extra_args: list[str]
) -> None:
    cmd = [
        str(hashcat),
        *extra_args,
        "-m",
        str(mode),
        "-a",
        "3",
        "-w",
        workload,
        "--status",
        "--status-timer",
        "30",
        str(hash_file),
        mask,
    ]
    subprocess.run(cmd, cwd=hashcat.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)


def run_hashcat_wordlist(hashcat: Path, hash_file: Path, mode: int, wordlist: Path, workload: str, extra_args: list[str]) -> None:
    cmd = [
        str(hashcat),
        *extra_args,
        "-m",
        str(mode),
        "-a",
        "0",
        "-w",
        workload,
        "--status",
        "--status-timer",
        "30",
        str(hash_file),
        str(wordlist),
    ]
    subprocess.run(cmd, cwd=hashcat.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)


def show_hashcat_password(hashcat: Path, hash_string: str, hash_file: Path, mode: int, extra_args: list[str] | None = None) -> str | None:
    completed = subprocess.run(
        [str(hashcat), *(extra_args or []), "-m", str(mode), str(hash_file), "--show"],
        cwd=hashcat.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in completed.stdout.splitlines():
        if not line.startswith(hash_string + ":"):
            continue
        return line[len(hash_string) + 1 :]
    return None


def verify_password(target: CrackTarget, password: str) -> bool:
    if not password or "exception" in password.lower() or "error" in password.lower():
        return False
    if target.kind == "pdf":
        return verify_pdf_password(target.path, password)
    if target.kind == "zip":
        return verify_zip_password(target.path, password)
    return False


def verify_pdf_password(path: Path, password: str) -> bool:
    try:
        from pypdf import PdfReader
    except ImportError:
        return True
    try:
        reader = PdfReader(str(path))
        if not reader.is_encrypted:
            return True
        return bool(reader.decrypt(password))
    except Exception:
        return False


def verify_zip_password(path: Path, password: str) -> bool:
    pwd = password.encode("utf-8")
    try:
        with zipfile.ZipFile(path) as archive:
            first_file = next((info for info in archive.infolist() if not info.is_dir()), None)
            if first_file is None:
                return True
            with archive.open(first_file, pwd=pwd) as source:
                source.read(1)
            return True
    except Exception:
        pass

    try:
        import pyzipper
    except ImportError:
        return False
    try:
        with pyzipper.AESZipFile(path) as archive:
            archive.setpassword(pwd)
            first_file = next((info for info in archive.infolist() if not info.is_dir()), None)
            if first_file is None:
                return True
            with archive.open(first_file) as source:
                source.read(1)
            return True
    except Exception:
        return False


def write_password_snippet(results: list[CrackResult], output_path: Path) -> None:
    cracked = [item for item in results if item.status == "cracked"]
    if not cracked:
        if output_path.exists():
            output_path.unlink()
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    by_filename = {item.target.filename: item.password for item in cracked}
    lines = [
        "# Copy these entries into financial_attachment_passwords.env after reviewing them locally.",
        "# Do not commit real password files or this generated snippet.",
        "FINANCIAL_ATTACHMENT_PASSWORD_BY_FILENAME_JSON="
        + json.dumps(by_filename, ensure_ascii=False),
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def persist_cracked_passwords(results: list[CrackResult], password_env: Path) -> int:
    cracked_attachments = [
        item
        for item in results
        if item.status == "cracked" and item.target.kind in {"zip", "pdf"} and item.password
    ]
    if not cracked_attachments:
        return 0

    values = read_env_assignments(password_env)
    by_filename = parse_json_object(
        values.get("FINANCIAL_ATTACHMENT_PASSWORD_BY_FILENAME_JSON", "{}")
    )
    zip_passwords = parse_json_list(values.get("FINANCIAL_ATTACHMENT_ZIP_PWD", "[]"))
    pdf_passwords = parse_json_list(values.get("FINANCIAL_ATTACHMENT_PDF_PWD", "[]"))
    changed = 0
    changed_targets = 0
    for item in cracked_attachments:
        item_changed = False
        filename = item.target.filename
        existing_key = find_case_insensitive_key(by_filename, filename)
        key = existing_key or filename
        current = normalize_password_value(by_filename.get(key))
        if item.password not in current:
            by_filename[key] = current + [item.password] if current else item.password
            item_changed = True
        type_passwords = zip_passwords if item.target.kind == "zip" else pdf_passwords
        if item.password not in type_passwords:
            type_passwords.append(item.password)
            item_changed = True
        if item_changed:
            changed += 1
            changed_targets += 1

    if not changed:
        return 0

    set_env_assignment(
        password_env,
        "FINANCIAL_ATTACHMENT_PASSWORD_BY_FILENAME_JSON",
        json.dumps(by_filename, ensure_ascii=False),
    )
    set_env_assignment(
        password_env,
        "FINANCIAL_ATTACHMENT_ZIP_PWD",
        json.dumps(zip_passwords, ensure_ascii=False, separators=(",", ":")),
    )
    set_env_assignment(
        password_env,
        "FINANCIAL_ATTACHMENT_PDF_PWD",
        json.dumps(pdf_passwords, ensure_ascii=False, separators=(",", ":")),
    )
    return changed_targets


def read_env_assignments(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = strip_optional_quotes(value.strip())
    return values


def strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): item for key, item in parsed.items()}


def parse_json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item)]


def normalize_password_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value is None:
        return []
    text = str(value)
    return [text] if text else []


def find_case_insensitive_key(data: dict[str, Any], key: str) -> str | None:
    lowered = key.lower()
    for existing_key in data:
        if existing_key.lower() == lowered:
            return existing_key
    return None


def set_env_assignment(env_path: Path, key: str, value: str) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    assignment = f"{key}={value}"
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        existing_key, _ = line.split("=", 1)
        if existing_key.strip() == key:
            lines[index] = assignment
            break
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(assignment)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_summary(
    results: list[CrackResult],
    output_path: Path,
    password_env: Path,
    persisted_count: int,
) -> None:
    cracked_count = sum(1 for item in results if item.status == "cracked")
    not_cracked_count = sum(1 for item in results if item.status == "not_cracked")
    error_count = sum(1 for item in results if item.status == "error")
    print("")
    print(
        f"完成：破解成功 {cracked_count}，未破解 {not_cracked_count}，错误 {error_count}。"
    )
    if persisted_count:
        print(f"已保存 {persisted_count} 条附件密码记录到：{password_env}")
    if cracked_count:
        print(f"已写入本地 env 片段：{output_path}")
        print(
            "下次运行会先尝试已保存密码；需要提取附件时运行：python financial_email_bot.py --stage extract"
        )


def print_targets(targets: list[CrackTarget]) -> None:
    print(f"待处理附件数：{len(targets)}")
    for index, target in enumerate(targets, start=1):
        print(f"[{index}] {target.kind.upper()} {target.path}")
        if target.bank_key or target.sent_at or target.subject:
            print(
                f"    bank={target.bank_key} sent_at={target.sent_at} subject={target.subject}"
            )


def print_tool_check(args: argparse.Namespace) -> None:
    checks = [
        ("hashcat", args.hashcat, resolve_executable(args.hashcat)),
        ("zip2john", args.zip2john, resolve_executable(args.zip2john)),
        ("pdf2john", args.pdf2john, resolve_executable(args.pdf2john)),
    ]
    for name, configured, resolved in checks:
        status = "OK" if resolved else "MISSING"
        print(f"{name}: {status} configured={configured or ''} resolved={resolved or ''}")
    perl = shutil.which("perl")
    print(f"perl: {'OK' if perl else 'MISSING'} resolved={perl or ''}")


def format_result(result: CrackResult, show_passwords: bool) -> str:
    if result.status == "cracked":
        password = result.password if show_passwords else mask_password(result.password)
        mode = result.mode if result.mode is not None else result.mask
        return f"  -> 已破解 mode={mode} mask={result.mask} password={password}"
    return f"  -> {result.status}: {result.reason}"


def read_json_list(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"JSON 文件必须是列表：{path}")
    return [item for item in data if isinstance(item, dict)]


def target_from_item(item: dict[str, Any]) -> CrackTarget:
    path = Path(str(item.get("path", "")))
    return CrackTarget(
        path=path,
        kind=extension_kind(path),
        filename=path.name,
        bank_key=str(item.get("bank_key", "")),
        subject=str(item.get("subject", "")),
        sent_at=str(item.get("sent_at", "")),
        status=str(item.get("status") or item.get("encrypted_status") or ""),
    )


def target_from_path(path: Path) -> CrackTarget:
    return CrackTarget(
        path=path,
        kind=extension_kind(path),
        filename=path.name,
        bank_key="",
        subject="",
        sent_at="",
        status="",
    )


def extension_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return "zip"
    if suffix == ".pdf":
        return "pdf"
    return "other"


def dedupe_targets(targets: list[CrackTarget]) -> list[CrackTarget]:
    seen: set[str] = set()
    result: list[CrackTarget] = []
    for target in targets:
        key = str(target.path)
        if key in seen:
            continue
        seen.add(key)
        result.append(target)
    return result


def resolve_executable(value: str | None) -> Path | None:
    if not value:
        return None
    expanded = Path(value).expanduser()
    if expanded.exists():
        return expanded
    found = shutil.which(value)
    return Path(found) if found else None


def executable_command(path: Path) -> list[str]:
    if path.suffix.lower() == ".py":
        return [sys.executable, str(path)]
    if path.suffix.lower() == ".pl":
        perl = shutil.which("perl")
        return [perl or "perl", str(path)]
    return [str(path)]


def find_john_tool(name: str) -> Path | None:
    candidates = [name, f"{name}.exe", f"{name}.py"]
    for candidate in candidates:
        resolved = resolve_executable(candidate)
        if resolved:
            return resolved

    for root in [Path("vendor"), Path("tools")]:
        if not root.exists():
            continue
        for candidate in root.rglob(f"{name}*"):
            if candidate.is_file():
                return candidate
    return None


def keep_hash(hash_file: Path, target: CrackTarget) -> Path:
    output_dir = Path("raw_data/financial_email/cracking_hashes")
    output_dir.mkdir(parents=True, exist_ok=True)
    kept = output_dir / f"{safe_stem(target.path)}.{target.kind}.hash"
    shutil.copy2(hash_file, kept)
    return kept


def safe_stem(path: Path) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", path.stem.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.strip("._") or "attachment"


def mask_password(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


if __name__ == "__main__":
    raise SystemExit(main())
