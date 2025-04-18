import os
import json
import pyodbc
import pandas as pd
import warnings
from datetime import datetime
from cryptography.fernet import Fernet
#from decouple import config  # pip install python-decouple
from myfunctions import query_yes_no
from dotenv import load_dotenv

orderclause = ''  # Initialize orderclause

# COLOR CLASS
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


# Load .env
load_dotenv()

# build odbc string
def build_odbc_string(params: dict) -> str:
    return ";".join(f"{k}={v}" for k, v in params.items()) + ";"

# Load environment variables
def load_db_config(build_odbc=True):
    key_path = os.getenv("DB_SECRET_KEY_PATH")
    enc_path = os.getenv("DB_ENCRYPTED_CONFIG_PATH")

    with open(key_path, "rb") as kf:
        key = kf.read()
    fernet = Fernet(key)

    with open(enc_path, "rb") as ef:
        encrypted = ef.read()

    config_data = json.loads(fernet.decrypt(encrypted))

    if build_odbc:
        return {env: build_odbc_string(cfg) for env, cfg in config_data.items()}
    else:
        return config_data


#Load configuration
conn_strings = load_db_config()


# --- Main Script Starts Here ---

warnings.filterwarnings('ignore')
os.system("cls" if os.name == "nt" else "clear")

# CHOOSE ENVIRONMENT
environment = query_yes_no("Do you want to parse a QA Template")
print(f'Your answer was: {environment}')
if environment:
    DB = "VAMOBILE"
    FORMATENV = color.GREEN + color.BOLD + "QA" + color.END
    cnxn_str = conn_strings["QA"]

else:
    DB = "VAMOBILE_PROD"
    FORMATENV = color.RED + color.BOLD + "PROD" + color.END
    cnxn_str = conn_strings["PROD"]
# CHOOSE TEMPLATE TYPE OLD/NEW
templatetype = query_yes_no("Parse NEW (Y) or OLD (n) Template ")
print(f'Your answer was: {templatetype}')
templatetable = "[SurveyGlobalTemplates]" if templatetype else "[SurveyTemplates]"

# PROVIDE TEMPLATE ID
print('################################')
entered_value = input('Enter TemplateID (int) to parse: ')
print('################################')

# Clean input
entered_value = entered_value.replace("'", "").replace('"', '')
if not entered_value.isdigit():
    print(f'"{entered_value}" is not an integer\n')
    exit()

templateID = int(entered_value)
print(f'TemplateID: {templateID}')
print('################################')

# BUILD QUERY
fieldsclause = "structure, Id as TemplateID, Name, EquipmentType, Version, Structure, Frontlines"
whereclause = f"where id in ({templateID}, {templateID+1})"
query = f"SELECT {fieldsclause} FROM {DB}.[dbo].{templatetable} {whereclause} {orderclause}"

# DB CONNECTION
cnxn = pyodbc.connect(cnxn_str)
cursor = cnxn.cursor()

pdf = pd.read_sql(query, cnxn).transpose()

if pdf.size == 0:
    print(f'\nNO TEMPLATES WITH ID = {templateID}.\n')
    cnxn.close()
    exit()

results = pdf.to_dict()
print(f'\n@@@@@@@@@@@@@@ FROM {FORMATENV} DB @@@@@@@@@@@@\n')
print(f"TemplateID  : {results[0]['TemplateID']}")
print(f"Name        : {results[0]['Name']}")
print(f"Version     : {results[0]['Version']}")
print(f"EqType      : {results[0]['EquipmentType']}")
print(f"FrontLines  : {results[0]['Frontlines']}")
print('\n@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n')
cnxn.close()

# --- Parse JSON Structure ---
print('\n' * 2)
print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@')

json_string = results[0]['Structure']
data = json.loads(json_string)

def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            if all(isinstance(item, (int, str)) for item in v):
                for i, item in enumerate(v):
                    items.append((f"{new_key}{sep}{i}", item))
            else:
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        for j, friend_item in flatten_dict(item, f"{new_key}{sep}{i}", sep=sep).items():
                            items.append((f"{j}_{i}", friend_item))
                    else:
                        raise ValueError(f"Unexpected item type {type(item)} in list {new_key}")
        else:
            items.append((new_key, v))
    return dict(items)

flat_dict = flatten_dict(data)
df = pd.DataFrame([flat_dict]).transpose()
df = df.rename(index=lambda x: str(x).replace('_questions_', '_question_'))

rows_with_duplicates = []
for index, row in df.iterrows():
    rows_with_duplicates.append((index, row))
    if "_question_" in str(index):
        new_index = str(index).replace("_question_", "_helptext_")
        rows_with_duplicates.append((new_index, row))

new_df = pd.DataFrame({index: row for index, row in rows_with_duplicates}).transpose()
new_df.rename(columns={0: "Label"}, inplace=True)
new_df['Position'] = range(1, len(new_df) + 1)
new_df['Type'] = new_df.index.str.split('_').str[2]
new_df['FL'] = "ALL"
new_df = new_df[['Position', 'Label','Type', 'FL']]

# Modify labels based on type
for index, row in new_df.iterrows():
    if row['Type'] == 'question':
        new_df.at[index, 'Label'] += '_lk'
    elif row['Type'] == 'helptext':
        new_df.at[index, 'Label'] += '_ilk'

# Save result to Excel
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
new_df.to_excel(f'output_{timestamp}.xlsx', header=True, index=False)

exit()
