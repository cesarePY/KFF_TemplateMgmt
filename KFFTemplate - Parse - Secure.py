import os
import json
import pyodbc
import pandas as pd
import warnings
from datetime import datetime
from cryptography.fernet import Fernet
# from decouple import config  # pip install python-decouple
from myfunctions import query_yes_no
from dotenv import load_dotenv

# Optional clause for ordering SQL results, currently not used
orderclause = ''

# Define ANSI color codes for terminal output formatting
class color:
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

# Load variables from a .env file into the environment, e.g., secret key paths
load_dotenv()

# Utility function to build an ODBC connection string from a dictionary of parameters
def build_odbc_string(params: dict) -> str:
    return ";".join(f"{k}={v}" for k, v in params.items()) + ";"

# Securely load encrypted DB config using Fernet encryption
def load_db_config(build_odbc=True):
    key_path = os.getenv("DB_SECRET_KEY_PATH")  # Path to encryption key
    enc_path = os.getenv("DB_ENCRYPTED_CONFIG_PATH")  # Path to encrypted config file

    # Load encryption key from file
    with open(key_path, "rb") as kf:
        key = kf.read()
    fernet = Fernet(key)  # Initialize Fernet with key

    # Read and decrypt the encrypted JSON config file
    with open(enc_path, "rb") as ef:
        encrypted = ef.read()

    config_data = json.loads(fernet.decrypt(encrypted))

    # Return as raw dict or build ODBC connection strings
    if build_odbc:
        return {env: build_odbc_string(cfg) for env, cfg in config_data.items()}
    else:
        return config_data

# Load database connection strings into a dictionary
conn_strings = load_db_config()

# --- Main Script Logic ---

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# Clear the console to improve UX
os.system("cls" if os.name == "nt" else "clear")

# Prompt user to select environment (QA or PROD)
environment = query_yes_no("Do you want to parse a QA Template")
print(f'Your answer was: {environment}')

# Set database name and display format based on environment
if environment:
    DB = "VAMOBILE"
    FORMATENV = color.GREEN + color.BOLD + "QA" + color.END
    file_env = "QA"
    cnxn_str = conn_strings["QA"]
else:
    DB = "VAMOBILE_PROD"
    FORMATENV = color.RED + color.BOLD + "PROD" + color.END
    file_env = "PROD"
    cnxn_str = conn_strings["PROD"]

# Prompt user to choose between OLD and NEW template schema
templatetype = query_yes_no("Parse NEW (Y) or OLD (n) Template ")
print(f'Your answer was: {templatetype}')
templatetable = "[SurveyGlobalTemplates]" if templatetype else "[SurveyTemplates]"

# Prompt user to enter a template ID
print('################################')
entered_value = input('Enter TemplateID (int) to parse: ')
print('################################')

# Sanitize input by stripping quotes and validating it as integer
entered_value = entered_value.replace("'", "").replace('"', '')
if not entered_value.isdigit():
    print(f'"{entered_value}" is not an integer\n')
    exit()

templateID = int(entered_value)
print(f'TemplateID: {templateID}')
print('################################')

# Construct the SQL query to fetch the template and its metadata
fieldsclause = "structure, Id as TemplateID, Name, EquipmentType, Version, Structure, Frontlines"
whereclause = f"where id in ({templateID}, {templateID+1})"
query = f"SELECT {fieldsclause} FROM {DB}.[dbo].{templatetable} {whereclause} {orderclause}"

# Execute query using pyodbc and load results into pandas DataFrame
cnxn = pyodbc.connect(cnxn_str)
cursor = cnxn.cursor()
pdf = pd.read_sql(query, cnxn).transpose()  # Transpose to ease dict conversion

# Exit early if no template found
if pdf.size == 0:
    print(f'\nNO TEMPLATES WITH ID = {templateID}.\n')
    cnxn.close()
    exit()

# Convert DataFrame to dict for structured access
results = pdf.to_dict()
print(f'\n@@@@@@@@@@@@@@ FROM {FORMATENV} DB @@@@@@@@@@@@\n')
print(f"TemplateID  : {results[0]['TemplateID']}")
print(f"Name        : {results[0]['Name']}")
print(f"Version     : {results[0]['Version']}")
print(f"EqType      : {results[0]['EquipmentType']}")
print(f"FrontLines  : {results[0]['Frontlines']}")
print('\n@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n')

# Capture template fields for use in output file name
template_name = results[0]['Name'].replace(" ", "_").replace("/", "-")
template_version = str(results[0]['Version']).replace(" ", "_").replace("/", "-")
equipment_type = results[0]['EquipmentType'].replace(" ", "_").replace("/", "-")

cnxn.close()

# --- Parse and Flatten JSON Template Structure ---
print('\n' * 2)
print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@')

# Parse the 'Structure' JSON string
json_string = results[0]['Structure']
data = json.loads(json_string)

# Recursively flatten nested dictionaries and lists
def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        # Generate new key using separator and parent prefix
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            # If value is a dictionary, recursively flatten it
            items.extend(flatten_dict(v, new_key, sep=sep).items())

        elif isinstance(v, list):
            # If list contains only basic types, enumerate values
            if all(isinstance(item, (int, str)) for item in v):
                for i, item in enumerate(v):
                    items.append((f"{new_key}{sep}{i}", item))
            else:
                # If list contains nested dicts, recursively flatten them
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        for j, friend_item in flatten_dict(item, f"{new_key}{sep}{i}", sep=sep).items():
                            items.append((f"{j}_{i}", friend_item))
                    else:
                        raise ValueError(f"Unexpected item type {type(item)} in list {new_key}")
        else:
            # For non-container types, store directly
            items.append((new_key, v))
    return dict(items)

# Flatten the JSON structure
flat_dict = flatten_dict(data)

# Convert to DataFrame and clean up keys for consistency
df = pd.DataFrame([flat_dict]).transpose()
df = df.rename(index=lambda x: str(x).replace('_questions_', '_question_'))

# Prepare to duplicate rows where needed
rows_with_duplicates = []
for index, row in df.iterrows():
    rows_with_duplicates.append((index, row))
    if "_question_" in str(index):
        new_index = str(index).replace("_question_", "_helptext_")
        rows_with_duplicates.append((new_index, row))

# Build final DataFrame for Excel output
new_df = pd.DataFrame({index: row for index, row in rows_with_duplicates}).transpose()
new_df.rename(columns={0: "Label"}, inplace=True)
new_df['Position'] = range(1, len(new_df) + 1)
new_df['Type'] = new_df.index.str.split('_').str[2]  # Extract type from index
new_df['FL'] = "ALL"
new_df = new_df[['Position', 'Label','Type', 'FL']]

# Add suffixes to label names for frontend logic
for index, row in new_df.iterrows():
    if row['Type'] == 'question':
        new_df.at[index, 'Label'] += '_lk'
    elif row['Type'] == 'helptext':
        new_df.at[index, 'Label'] += '_ilk'

# Export to Excel with enriched filename including env, name, version, and eq type
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"{file_env}_{template_name}_{template_version}_{equipment_type}_{timestamp}.xlsx"
new_df.to_excel(filename, header=True, index=False)

exit()
