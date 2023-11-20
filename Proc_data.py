import os

import pandas as pd


class FileSearch:
    """
    Provides methods to search for files within a specified folder based on keywords and extensions.
    """

    def __init__(self, folder_path):
        """
        Initializes a FileSearch object with the specified folder path.

        Args:
        - folder_path (str): The path of the folder to search for files.
        """
        self.folder_path = folder_path

    def find_files_with_keyword(self, keyword) -> list:
        """
        Finds files within the folder containing a specific keyword.

        Args:
        - keyword (str): The keyword to search for in the file names.

        Returns:
        - list: A list of file paths that contain the specified keyword.
        """
        file_list = []
        # 遍历文件夹内所有文件
        for root, _, files in os.walk(self.folder_path):
            for file in files:
                # 匹配关键字
                if keyword in file:
                    file_list.append(os.path.join(root, file))
        return file_list

    def find_files_with_extension_and_keyword(self, extension, keyword) -> list:
        """
        Finds files within the folder matching a specific extension and containing a keyword.

        Args:
        - extension (str): The file extension to filter by (e.g., '.txt', '.csv').
        - keyword (str): The keyword to search for in the file names.

        Returns:
        - list: A list of file paths that match the specified extension and contain the keyword.
        """
        file_list = []
        # 遍历文件夹内所有文件
        for root, _, files in os.walk(self.folder_path):
            for file in files:
                # 检查文件扩展名和匹配关键字
                if file.endswith(extension) and keyword in file:
                    file_list.append(os.path.join(root, file))
        return file_list


"""
[flag_word] : [begin_word, end_word, del_keyword1,...]
"""


class CSVHandler:
    def __init__(
        self, file_path: str, columns_name: list, flag_words: list, card_num: list
    ):
        self._file_path = file_path
        self._columns_name = columns_name
        self._flag_words = flag_words
        self._card_num = card_num
        self._is_icbc = "no"
        self._is_wechat = "no"
        self._is_alipay = "no"
        self._temp_csv = "../Data/temp.csv"
        if os.path.exists(self._temp_csv):
            os.remove(self._temp_csv)

        if "icbc" in file_path:
            self._is_icbc = "yes"
        elif "微信" in file_path:
            self._is_wechat = "yes"
        elif "alipay" in file_path:
            self._is_alipay = "yes"

    @classmethod
    def icbc(cls, file_path: str, columns_name: list, flag_words: list, card_num: list):
        return cls(
            file_path=file_path,
            columns_name=columns_name,
            flag_words=flag_words,
            card_num=card_num,
        )

    @classmethod
    def wechat(cls, file_path: str, columns_name: list):
        return cls(
            file_path=file_path, columns_name=columns_name, flag_words=[], card_num=[]
        )

    @classmethod
    def alipay(cls, file_path: str, columns_name: list):
        return cls(
            file_path=file_path, columns_name=columns_name, flag_words=[], card_num=[]
        )

    def extract_data(self):
        # Preprocess CSV file based on the detected type
        self._preprocess_csv()

        # Read and preprocess the CSV file
        self._data = self._read_and_preprocess_csv()
        # Process self._data according to different types
        if not self._data.empty:
            if self._is_icbc == "yes":
                """
                # ICBC-specific data processing
                # 对df进行切片处理
                """
                # 1.切掉尾巴
                df_end = self._get_index_with_keyword_in_col(
                    self._flag_words[1], self._columns_name[0]
                )
                self._data = self._data.iloc[: df_end[0] + 1]

                # 2.提取卡号rows
                self._data = self._data.iloc[
                    self._get_rows_index_with_feature_list(
                        self._columns_name[0], self._card_num
                    )
                ]
        return self._data

    def _preprocess_csv(self):
        if self._is_wechat == "yes":
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                with open(self._temp_csv, "w", encoding="utf-8") as f:
                    for i, line in enumerate(lines):
                        if "微信支付账单明细列表" in line:
                            f.writelines(lines[i + 1 :])
                            break
                    self._file_path = self._temp_csv
            except FileNotFoundError:
                print("File not found.")
        elif self._is_alipay == "yes":
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                with open(self._temp_csv, "w", encoding="utf-8") as f:
                    for i, line in enumerate(lines):
                        if "支付宝（中国）网络技术有限公司  电子客户回单" in line:
                            f.writelines(lines[i + 1 :])
                            break
                    self._file_path = self._temp_csv
            except FileNotFoundError:
                print("File not found.")

    def _read_and_preprocess_csv(self, encoding="utf-8"):
        try:
            df = pd.read_csv(self._file_path, encoding=encoding)

            # 生成新列名的列表
            df_cols = df.shape[1]
            new_columns = [col for col in self._columns_name]
            if df_cols > len(new_columns):
                for i in range(df_cols - len(new_columns)):
                    new_columns.append("Column_" + str(i + 1))

            # 使用新列名重新命名df的列
            df.columns = new_columns
            # Fill the NaN with "No_data"
            df.fillna("No_data", inplace=True)
            return df
        except FileNotFoundError:
            print("File not found.")
            return pd.DataFrame()

    def _get_index_with_keyword_in_col(self, keyword: str, col: str) -> list:
        """
        Retrieves indexes of rows in the DataFrame where a specific column contains the given keyword.

        Args:
        - keyword (str): The keyword to search for within the specified column.
        - col (str): The name of the column in which to search for the keyword.

        Returns:
        - list: A list containing the indexes of rows where the specified column contains the keyword.
                Returns an empty list if the column doesn't exist or if no matches are found.

        Note:
        - Case-sensitive matching is applied to the keyword.
        - If the keyword is found as a substring in the column, the row index is included in the result.
        - Uses string representation (astype(str)) of the column to search for the keyword.
        """
        # Check if the column exists in the DataFrame
        if col in self._data.columns:
            # Filter rows where the column contains the keyword
            indexes_with_keyword = self._data[
                self._data[col].astype(str).str.contains(keyword, na=False)
            ].index
            return indexes_with_keyword.tolist()
        else:
            return []  # Return an empty list if the column doesn't exist

    def _get_rows_index_with_feature_list(self, col, feature_list: list) -> list:
        """
        Retrieves the indices of rows containing specified features within a column.

        This method searches for specified features within a particular column of the dataset.
        If the specified column does not exist, it returns an empty list.

        Args:
        - self: The instance of the class.
        - col (str): The column in the dataset to search for features.
        - feature_list (list): A list of features to match within the column.

        Returns:
        - list: A list containing the indices of rows where any feature in the
          feature_list is present within the specified column. Returns an empty list
          if the column doesn't exist in the DataFrame.
        """
        # Check if the column exists in the DataFrame
        if col in self._data.columns:
            # Filter rows where the column contains the keyword in the feature_list
            matching_rows = self._data[
                self._data[col].apply(
                    lambda x: any(feature in x for feature in feature_list)
                )
            ].index
            return matching_rows.tolist()
        else:
            return []  # Return an empty list if the column doesn't exist

    def _get_index_with_feature_row(self, feature_row: list, df_range: list):
        # WARN: Useless function, got a better way!
        """
        Extracts indexes of rows in a specified range of the DataFrame where all values match a given feature_row.

        Args:
        - feature_row (list): A list containing values to match against DataFrame rows.
        - df_range (list): A list specifying the start and end index of the range to search within the DataFrame.
                           Should be a list with two elements [start_index, end_index].

        Returns:
        - list: A list containing the indexes of rows where all values match the feature_row within the specified range.
                Returns an empty list if the inputs are invalid or if no matching rows are found.
        """
        # Check if df_range is valid and feature_row is of the same length as DataFrame columns
        if (
            len(df_range) != 2
            or df_range[0] >= df_range[1]
            or not isinstance(feature_row, list)
        ):
            return []  # Return empty list for invalid inputs

        # Extract the specified range from the DataFrame
        df = self._data.iloc[df_range[0] : df_range[1] + 1]

        # Check if feature_row length matches DataFrame columns
        if len(feature_row) != len(df.columns):
            return (
                []
            )  # Return empty list if feature_row length doesn't match DataFrame columns

        # Filter rows where all values match the feature_row
        matching_rows = df[(df == feature_row).all(axis=1)].index

        return matching_rows.tolist()


def test_icbc():
    file_path = "../data/"
    # file_path = "d:/cloudstation/python/project/2019_account_book/csv"
    extension = ".csv"
    keyword = "icbc"
    file = FileSearch(file_path)
    file_path = file.find_files_with_extension_and_keyword(
        extension, keyword
    )  # 替换为你的 csv 文件路径

    print(file_path)
    column_name = [
        "卡号后四位",
        "交易日",
        "记账日",
        "交易类型",
        "商户名称/城市",
        "交易金额/币种",
        "记账金额/币种",
    ]

    flag_words = [
        "主卡",
        "积",
        "副卡",
    ]
    card_num = ["2481"]
    csv_handler = CSVHandler.icbc(file_path[0], column_name, flag_words, card_num)
    csv_data = csv_handler.extract_data()

    print(csv_data)


def test_wechat():
    file_path = "../data/"
    # file_path = "d:/cloudstation/python/project/2019_account_book/csv"
    extension = ".csv"
    keyword = "微信"
    file = FileSearch(file_path)
    file_path = file.find_files_with_extension_and_keyword(extension, keyword)
    print(file_path)
    columns_name = [
        "交易时间",
        "交易类型",
        "交易对方",
        "商品",
        "收/支",
        "金额(元)",
        "支付方式",
        "当前状态",
        "交易单号",
        "商户单号",
        "备注",
    ]
    csv_handler = CSVHandler.wechat(file_path[0], columns_name)
    csv_data = csv_handler.extract_data()

    print(csv_data)


def test_alipay():
    file_path = "../data/"
    extension = ".csv"
    keyword = "alipay"
    file = FileSearch(file_path)
    file_path = file.find_files_with_extension_and_keyword(extension, keyword)
    print(file_path[0])
    columns_name = [
        "交易时间",
        "交易分类",
        "交易对方",
        "对方账号",
        "商品说明",
        "收/支",
        "金额",
        "收/付款方式",
        "交易状态",
        "交易订单号",
        "商家订单号",
        "备注",
    ]
    csv_handler = CSVHandler.alipay(file_path[0], columns_name)
    csv_data = csv_handler.extract_data()
    print(csv_data)


if __name__ == "__main__":
    test_icbc()
    test_wechat()
    test_alipay()
