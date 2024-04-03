import pandas as pd

# Load your dataset
file_path = './datasets/allgrades-unformatted.csv'  # Update this to the path of your file
df = pd.read_csv(file_path)

df = df.fillna(0)
print(df.head(5))

df = df.iloc[1:]

# Find all quiz columns
quiz_columns = [col for col in df.columns if 'Quiz' in col and 'LOA' not in col and 'weight' in col]

for quiz_col in quiz_columns:
    split = quiz_col.split(" ")
    # Find LOA-Quiz column corresponding to the Quiz column
    loa_quiz_col = [col for col in df.columns if (f'LOA-{split[0]}{str(split[1])}' in col or f'LOA-{split[0]} {str(split[1])}' in col)]
    print(loa_quiz_col)
    if loa_quiz_col:
        loa_quiz_col = loa_quiz_col[0]  # There should be only one matching column
        # Convert N/A to 0 in the LOA-Quiz column
        df[loa_quiz_col] = df[loa_quiz_col].replace('N/A', 0).fillna(0).astype(float)
        # Add the LOA-Quiz scores to the Quiz scores
        df[quiz_col] = df[quiz_col].astype(float) + df[loa_quiz_col].astype(float)
        df[quiz_col].loc[1] /= 2.0
        # # Drop the LOA-Quiz column as it's no longer needed
        # df.drop(columns=[loa_quiz_col], inplace=True)

# Show the updated dataframe head to verify the changes
print(df.iloc[7, :10])

# Step 1: Filter required columns
keywords = ['standard', 'medium', 'heavy']
# Keep columns that contain any of the keywords or are 'Student' or 'SIS Login ID', ignoring case
columns_to_keep = [col for col in df.columns if any(keyword.lower() in col.lower() for keyword in keywords) 
                   or col in ['Student', 'SIS Login ID']]
df_filtered = df[columns_to_keep]


# Step 2: Convert grades to decimals
# Find the row with 'Points Possible' (assuming it's the second row)
points_possible = df_filtered.iloc[0]
print(df_filtered.head(5))
print(points_possible)
# Convert grades, treating 'N/A' as 0
for col in df_filtered.columns[2:]:  # Skip 'Student' and 'SIS Login ID' columns
    # Convert all 'N/A' to 0, coerce any errors, fill NaN with 0, and convert to float
    df_filtered[col] = pd.to_numeric(df_filtered[col].replace('N/A', 0), errors='coerce').fillna(0).astype(float)
    
    # Safely divide the values in the DataFrame using .loc to avoid the SettingWithCopyWarning
    df_filtered.loc[:, col] = df_filtered[col] / float(points_possible[col])

df_filtered = df_filtered.loc[:, ~df_filtered.columns.str.contains('LOA')]

# Remove the 'Points Possible' row to leave only student data
df_final = df_filtered.drop(1).reset_index(drop=True)


# Step 3: Save the modified dataframe to a new CSV file
output_file_path = './datasets/allgrades-temp.csv'  # Update this to your desired output path
df_final.to_csv(output_file_path, index=False)

print("The CSV file has been saved to:", output_file_path)
