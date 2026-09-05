import pandas as pd

file_path = r"C:\nipuni-software\Testings\Daniel_testing_1.xlsx"

print("\nReading Excel...")
print("File:", file_path)

df = pd.read_excel(
    file_path,
    sheet_name=0,
    header=None
)

print("\n========================================")
print("SHAPE")
print("========================================")

print("Rows:", df.shape[0])
print("Columns:", df.shape[1])


print("\n========================================")
print("COLUMN POSITIONS")
print("========================================")

for i in range(df.shape[1]):

    values = (
        df.iloc[:, i]
        .dropna()
        .astype(str)
        .head(15)
        .tolist()
    )

    print(
        f"\nCOLUMN {i}:"
    )

    print(
        " | ".join(values)
    )


print("\n========================================")
print("FIRST 20 ROWS")
print("========================================")

pd.set_option(
    "display.max_columns",
    None
)

pd.set_option(
    "display.width",
    500
)

pd.set_option(
    "display.max_colwidth",
    50
)

print(
    df.head(20).to_string(
        index=True,
        header=False
    )
)


print("\n========================================")
print("DONE")
print("========================================")