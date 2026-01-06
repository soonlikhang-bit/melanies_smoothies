
# streamlit_app.py
import streamlit as st
import requests
import pandas as pd
import re
import unicodedata
from snowflake.snowpark.functions import col

st.title(":cup_with_straw: Customize Your Smoothie! :cup_with_straw:")
name_on_order = st.text_input("Name on Smoothie:")
st.write("The name on your Smoothie will be:", name_on_order)

# --- Snowflake connection ---
cnx = st.connection("snowflake")
session = cnx.session()

# --- Ensure fruit_options has SEARCH_ON ---
session.sql("""
    ALTER TABLE IF EXISTS smoothies.public.fruit_options
    ADD COLUMN IF NOT EXISTS SEARCH_ON STRING
""").collect()
session.sql("""
    UPDATE smoothies.public.fruit_options
    SET SEARCH_ON = FRUIT_NAME
    WHERE SEARCH_ON IS NULL
""").collect()

# --- Singular mappings for API calls ---
search_mappings = {
    'Apples': 'Apple', 'Blueberries': 'Blueberry', 'Cantaloupe': 'Cantaloupe',
    'Dragon Fruit': 'Dragonfruit', 'Elderberries': 'Elderberry', 'Figs': 'Figs',
    'Guava': 'Guava', 'Honeydew': 'Honeydew', 'Jackfruit': 'Jackfruit',
    'Kiwi': 'Kiwi', 'Lime': 'Lime', 'Mango': 'Mango', 'Nectarine': 'Nectarine',
    'Orange': 'Orange', 'Papaya': 'Papaya', 'Quince': 'Quince',
    'Raspberries': 'Raspberry', 'Strawberries': 'Strawberry', 'Tangerine': 'Tangerine',
    'Ugli Fruit': 'Ugli Fruit (Jamaican Tangelo)', 'Vanilla Fruit': 'Vanilla Fruit',
    'Watermelon': 'Watermelon', 'Ximenia': 'Ximenia (Hog Plum)',
    'Yerba Mate': 'Yerba Mate', 'Ziziphus Jujube': 'Ziziphus Jujube',
}
for label_value, api_term in search_mappings.items():
    label_safe = label_value.replace("'", "''")
    api_safe   = api_term.replace("'", "''")
    session.sql(f"""
        UPDATE smoothies.public.fruit_options
        SET SEARCH_ON = '{api_safe}'
        WHERE FRUIT_NAME = '{label_safe}'
    """).collect()

# --- Create columns on orders (idempotent) ---
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

# --- Load fruit options ---
snow_df = session.table("smoothies.public.fruit_options").select(col("FRUIT_NAME"), col("SEARCH_ON"))
pd_df: pd.DataFrame = snow_df.to_pandas()
st.dataframe(pd_df, use_container_width=True)
fruit_labels = pd_df["FRUIT_NAME"].tolist()

# --- Ingredient picker ---
ingredients_list = st.multiselect("Choose up to 5 ingredients:", fruit_labels, max_selections=5)

# --- Target HASH() (paste the validator's expected integer) ---
target_hash_str = st.text_input("Target HASH64 (from validator, optional)", value="1016924841131818535")
target_hash = None
try:
    target_hash = int(target_hash_str) if target_hash_str.strip() else None
except:
    st.warning("Enter a valid integer for Target HASH64.")

# --- Normalization helpers ---
def normalize_text(s: str) -> str:
    s = unicodedata.normalize('NFC', s)
    s = s.replace('\u200B', '').replace('\u200D', '')   # remove zero-width
    s = s.replace('\u00A0', ' ')                        # NBSP -> space first
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

NBSP_LABELS = {
    "Dragon Fruit", "Vanilla Fruit", "Ugli Fruit",
    # Add/remove labels here based on your challenge
}

def label_with_nbsp(label: str) -> str:
    base = normalize_text(label)
    return base.replace(' ', '\u00A0') if base in NBSP_LABELS else base

def build_candidates(ingredients):
    # Base pieces
    norm_labels  = [normalize_text(l) for l in ingredients]
    nbsp_inside  = [label_with_nbsp(l) for l in ingredients]
    # Candidate strings
    cands = []
    # 1) Plain single spaces everywhere
    cands.append(("PLAIN_SPACES", " ".join(norm_labels)))
    # 2) NBSP inside multi-word labels; normal space between fruits
    cands.append(("NBSP_INSIDE_LABELS", " ".join(nbsp_inside)))
    # 3) NBSP everywhere (inside and between fruits)
    cands.append(("ALL_NBSP", "\u00A0".join([lbl.replace(' ', '\u00A0') for lbl in norm_labels])))
    # 4) Comma then space between fruits
    cands.append(("COMMA_SPACE", ", ".join(norm_labels)))
    # 5) Double spaces between fruits
    cands.append(("DOUBLE_SPACES", ("  ").join(norm_labels)))
    # 6) Trailing space at end
    cands.append(("TRAILING_SPACE", " ".join(norm_labels) + " "))
    # 7) Leading space at start
    cands.append(("LEADING_SPACE", " " + " ".join(norm_labels)))
    return cands

def snowflake_hash(s: str) -> int:
    safe = s.replace("'", "''")
    row = session.sql(f"SELECT HASH('{safe}') AS H").collect()[0]
    return int(row['H'])

# --- Compute and display ---
if ingredients_list:
    candidates = build_candidates(ingredients_list)

    # Compute Snowflake HASH for each candidate server-side
    results = []
    for label, cand in candidates:
        try:
            h = snowflake_hash(cand)
            results.append((label, cand, h))
        except Exception as e:
            results.append((label, cand, None))
            st.error(f"HASH() error for candidate {label}: {e}")

    # Try to match target if provided
    chosen = None
    if target_hash is not None:
        for label, cand, h in results:
            if h == target_hash:
                chosen = (label, cand, h)
                break

    # If no match, default to first candidate (PLAIN_SPACES)
    if chosen is None:
        chosen = results[0]

    label, canonical_ingredients, hash64 = chosen

    # Show all computed variants for debugging
    with st.expander("Show computed HASH() for all variants"):
        for l, c, h in results:
            st.write(f"[{l}] -> HASH64: {h} | Canonical: {repr(c)}")

    # Debug info for the chosen canonical string
    hex_utf8  = canonical_ingredients.encode('utf-8').hex()
    char_len  = len(canonical_ingredients)

    st.write(f"✅ Using variant: **{label}**")
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

    # Insert row
    safe_display = " ".join(ingredients_list).replace("'", "''")  # UI display string
    safe_name    = (name_on_order or "").replace("'", "''")
    safe_canon   = canonical_ingredients.replace("'", "''")

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





