import pandas as pd

# Load your dataset
file_path = './datasets/allgrades-unformatted.csv'  # Update this to the path of your file
df = pd.read_csv(file_path)

print(df.head(5))

# Step 1: Filter required columns
keywords = ['standard', 'medium', 'heavy']
# Keep columns that contain any of the keywords or are 'Student' or 'SIS Login ID', ignoring case
columns_to_keep = [col for col in df.columns if any(keyword.lower() in col.lower() for keyword in keywords) 
                   or col in ['Student', 'SIS Login ID']]
df_filtered = df[columns_to_keep]

print(df_filtered.head(5))

# Step 2: Convert grades to decimals
# Find the row with 'Points Possible' (assuming it's the second row)
points_possible = df_filtered.iloc[1]
# Convert grades, treating 'N/A' as 0
for col in df_filtered.columns[2:]:  # Skip 'Student' and 'SIS Login ID' columns
    df_filtered[col] = pd.to_numeric(df_filtered[col].replace('N/A', 0), errors='coerce').fillna(0)
    df_filtered[col] = df_filtered[col].astype(float) / float(points_possible[col])

# Remove the 'Points Possible' row to leave only student data
df_final = df_filtered.drop(1).reset_index(drop=True)

# Step 3: Save the modified dataframe to a new CSV file
output_file_path = './datasets/allgrades.csv'  # Update this to your desired output path
df_final.to_csv(output_file_path, index=False)

print("The CSV file has been saved to:", output_file_path)
