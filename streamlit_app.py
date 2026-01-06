
# streamlit_app.py
import streamlit as st
import requests
import pandas as pd
import re
import unicodedata
from snowflake.snowpark.functions import col

# -----------------------------
# Choose the rule that matches the validator
# -----------------------------
# "PLAIN"               → normal spaces everywhere
# "NBSP_INSIDE_LABELS"  → NBSP within multi-word labels, normal space between fruits
# "ALL_NBSP"            → NBSP everywhere (inside labels AND between fruits)
EXPECTED_RULE = "PLAIN"

# Multi-word labels that (optionally) get NBSP between words
NBSP_LABELS = {
    "Dragon Fruit",
    "Vanilla Fruit",
    "Ugli Fruit",
    # Add/remove as your validator requires
}

# -----------------------------
# Helpers
# -----------------------------
def normalize_text(s: str) -> str:
    """Unicode normalize, remove zero-widths, collapse spaces to a single ASCII space."""
    s = unicodedata.normalize('NFC', s)
    s = s.replace('\u200B', '').replace('\u200D', '')   # zero-width chars
    s = s.replace('\u00A0', ' ')                        # normalize NBSP to space first
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def label_with_nbsp(label: str) -> str:
    """Use NBSP between words only for labels listed in NBSP_LABELS."""
    base = normalize_text(label)
    if base in NBSP_LABELS:
        return base.replace(' ', '\u00A0')
    return base

def build_canonical(ingredients_list):
    """Construct canonical string per EXPECTED_RULE."""
    normalized_labels = [normalize_text(l) for l in ingredients_list]

    if EXPECTED_RULE == "PLAIN":
        return " ".join(normalized_labels)

    if EXPECTED_RULE == "NBSP_INSIDE_LABELS":
        glued = [label_with_nbsp(l) for l in normalized_labels]
        return " ".join(glued)

    if EXPECTED_RULE == "ALL_NBSP":
        glued = [normalize_text(l).replace(' ', '\u00A0') for l in normalized_labels]
        return '\u00A0'.join(glued)

    # Fallback
    return " ".join(normalized_labels)

# -----------------------------
# UI
# -----------------------------
st.title(":cup_with_straw: Customize Your Smoothie! :cup_with_straw:")
st.caption(f"Canonical rule in use: **{EXPECTED_RULE}**")
name_on_order = st.text_input("Name on Smoothie:")
st.write("The name on your Smoothie will be:", name_on_order)

# -----------------------------
# Snowflake connection & setup
# -----------------------------
cnx = st.connection("snowflake")
session = cnx.session()

# Ensure SEARCH_ON exists and is seeded
session.sql("""
    ALTER TABLE IF EXISTS smoothies.public.fruit_options
    ADD COLUMN IF NOT EXISTS SEARCH_ON STRING
""").collect()

session.sql("""
    UPDATE smoothies.public.fruit_options
    SET SEARCH_ON = FRUIT_NAME
    WHERE SEARCH_ON IS NULL
""").collect()

# Map UI labels to API singulars
search_mappings = {
    'Apples': 'Apple',
    'Blueberries': 'Blueberry',
    'Cantaloupe': 'Cantaloupe',
    'Dragon Fruit': 'Dragonfruit',
    'Elderberries': 'Elderberry',
    'Figs': 'Figs',
    'Guava': 'Guava',
    'Honeydew': 'Honeydew',
    'Jackfruit': 'Jackfruit',
    'Kiwi': 'Kiwi',
    'Lime': 'Lime',
    'Mango': 'Mango',
    'Nectarine': 'Nectarine',
    'Orange': 'Orange',
    'Papaya': 'Papaya',
    'Quince': 'Quince',
    'Raspberries': 'Raspberry',
    'Strawberries': 'Strawberry',
    'Tangerine': 'Tangerine',
    'Ugli Fruit': 'Ugli Fruit (Jamaican Tangelo)',
    'Vanilla Fruit': 'Vanilla Fruit',
    'Watermelon': 'Watermelon',
    'Ximenia': 'Ximenia (Hog Plum)',
    'Yerba Mate': 'Yerba Mate',
    'Ziziphus Jujube': 'Ziziphus Jujube',
}
for label_value, api_term in search_mappings.items():
    label_safe = label_value.replace("'", "''")
    api_safe   = api_term.replace("'", "''")
    session.sql(f"""
        UPDATE smoothies.public.fruit_options
        SET SEARCH_ON = '{api_safe}'
        WHERE FRUIT_NAME = '{label_safe}'
    """).collect()

# Create target columns (idempotent)
session.sql("""
    ALTER TABLE IF EXISTS smoothies.public.orders
    ADD COLUMN IF NOT EXISTS INGREDIENTS_CANON STRING
""").collect()
session.sql("""
    ALTER TABLE IF EXISTS smoothies.public.orders
    ADD COLUMN IF NOT EXISTS HEX_UTF8 STRING
""").collect()
session.sql("""
    ALTER TABLE IF EXISTS smoothies.public.orders
    ADD COLUMN IF NOT EXISTS LEN NUMBER
""").collect()
session.sql("""
    ALTER TABLE IF EXISTS smoothies.public.orders
    ADD COLUMN IF NOT EXISTS HASH64 NUMBER(19,0)
""").collect()

# -----------------------------
# Load fruit options
# -----------------------------
snow_df = session.table("smoothies.public.fruit_options").select(
    col("FRUIT_NAME"), col("SEARCH_ON")
)
pd_df: pd.DataFrame = snow_df.to_pandas()
st.dataframe(pd_df, use_container_width=True)

fruit_labels = pd_df["FRUIT_NAME"].tolist()

# -----------------------------
# Ingredient picker
# -----------------------------
ingredients_list = st.multiselect(
    "Choose up to 5 ingredients:",
    fruit_labels,
    max_selections=5,
)

# -----------------------------
# Handle selection: build canonical and compute HASH() in Snowflake
# -----------------------------
if ingredients_list:
    display_ingredients   = " ".join(ingredients_list)     # what the user sees
    canonical_ingredients = build_canonical(ingredients_list)

    # Local debug values
    hex_utf8 = canonical_ingredients.encode('utf-8').hex()
    char_len = len(canonical_ingredients)

    # Compute HASH() in Snowflake for the canonical string
    # (HASH returns NUMBER(19,0), signed 64-bit)
    safe_canon = canonical_ingredients.replace("'", "''")
    hash_row   = session.sql(f"SELECT HASH('{safe_canon}') AS H").collect()[0]
    hash64     = int(hash_row['H'])

    # Show debug to the user
    st.write(f"Ingredients (canonical): {canonical_ingredients}")
    st.write(f"UTF-8 HEX: {hex_utf8}")
    st.write(f"Char LEN: {char_len}")
    st.write(f"Snowflake HASH() (64-bit): {hash64}")

    # Nutrition info
    for fruit_label in ingredients_list:
        row_match = pd_df.loc[pd_df["FRUIT_NAME"] == fruit_label, "SEARCH_ON"]
        search_on = str(row_match.iloc[0]) if not row_match.empty else fruit_label
        st.subheader(f"{fruit_label} Nutrition Information")
        try:
            response = requests.get(f"https://my.smoothiefroot.com/api/fruit/{search_on}")
            if response.ok:
                st.dataframe(response.json(), use_container_width=True)
            else:
                st.warning(f"Could not fetch info for '{fruit_label}' (searched as '{search_on}'). Status: {response.status_code}")
        except Exception as e:
            st.error(f"Error fetching data for '{fruit_label}': {e}")

    # Prepare safe SQL insert
    safe_display = display_ingredients.replace("'", "''")
    safe_name    = (name_on_order or "").replace("'", "''")

    insert_sql = f"""
        INSERT INTO smoothies.public.orders
            (INGREDIENTS, INGREDIENTS_CANON, NAME_ON_ORDER, HEX_UTF8, LEN, HASH64)
        VALUES
            ('{safe_display}', '{safe_canon}', '{safe_name}', '{hex_utf8}', {char_len}, {hash64})
    """

    if st.button("Submit Order"):
        try:
            session.sql(insert_sql).collect()
            st.success("Your Smoothie is ordered!", icon="✅")
        except Exception as e:
            st.error(f"Order submission failed: {e}")




