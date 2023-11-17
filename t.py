import pandas as pd

# 创建一个示例 DataFrame
data = {
    "Name": ["Alice", "Bob", "Charlie", "David"],
    "Age": [25, 30, 22, 35],
    "City": ["New York", "San Francisco", "Los Angeles", "Chicago"],
}

df = pd.DataFrame(data)

# 要查找的特征列表
l = ["Bob", "30", "San Francisco"]

# 使用布尔索引找到符合特征的行
matching_rows = df[df.isin(l).any(axis=1)].index

print(data)
# 打印结果
print(matching_rows.tolist())
