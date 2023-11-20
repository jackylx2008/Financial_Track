try:
    with open("../Data/微信支付账单(20230801-20231101).csv", "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open("../Data/temp.csv", "w", encoding="utf-8") as f:
        for i, line in enumerate(lines):
            if "微信支付账单明细列表" in line:
                f.writelines(lines[i + 1 :])
                break
        # self._file_path = "../Data/temp.csv"
except FileNotFoundError:
    print("File not found.")
