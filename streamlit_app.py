
# streamlit_app.py
import streamlit as st
import requests
import pandas as pd
import re
import unicodedata
from snowflake.snowpark.functions import col

# --------------------------------------------------------------------
# Config: set to True if you want INGREDIENTS to store the CANONICAL
#         string (with trailing space). If False, INGREDIENTS keeps a
#         UI-friendly value and CANONICAL is stored in INGREDIENTS_CANON.
# --------------------------------------------------------------------
STORE_CANON_IN_INGREDIENTS = True

# --------------------------------------------------------------------
# App Header
# --------------------------------------------------------------------
st.title(":cup_with_straw: Customize Your Smoothie! :cup_with_straw:")
st.caption("Canonicalization rule: **single spaces between fruits + ONE trailing space**")
name_on_order = st.text_input("Name on Smoothie:")
st.write("The name on your Smoothie will be:", name_on_order)

# --------------------------------------------------------------------
# Snowflake connection & setup
# --------------------------------------------------------------------
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

# Map UI labels to API search spellings (singulars)
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

# Ensure target columns exist on orders table
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

# --------------------------------------------------------------------
# Load fruit options for UI
# --------------------------------------------------------------------
snow_df = session.table("smoothies.public.fruit_options").select(
    col("FRUIT_NAME"), col("SEARCH_ON")
)
pd_df: pd.DataFrame = snow_df.to_pandas()
st.dataframe(pd_df, use_container_width=True)

fruit_labels = pd_df["FRUIT_NAME"].tolist()

# --------------------------------------------------------------------
# Ingredient picker
# --------------------------------------------------------------------
ingredients_list = st.multiselect(
    "Choose up to 5 ingredients:",
    fruit_labels,
    max_selections=5,
)

# --------------------------------------------------------------------
# Normalizer (prevents hidden Unicode surprises)
# --------------------------------------------------------------------
def normalize_text(s: str) -> str:
    s = unicodedata.normalize('NFC', s)
    s = s.replace('\u200B', '').replace('\u200D', '')  # remove zero-width chars
    s = s.replace('\u00A0', ' ')                       # NBSP -> normal space
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

# --------------------------------------------------------------------
# Handle selection
# --------------------------------------------------------------------
if ingredients_list:
    # 1) Build canonical: single spaces between fruits + ONE trailing space
    norm_labels = [normalize_text(l) for l in ingredients_list]
    canonical_ingredients = " ".join(norm_labels) + " "     # <-- required trailing space
    display_ingredients   = " ".join(ingredients_list)      # UI-only (no trailing space)

    # 2) Compute *in Snowflake* the LEN / HEX / HASH for the canonical string
    #    to guarantee exact parity with validator
    safe_canon = canonical_ingredients.replace("'", "''")
    meta_row = session.sql(f"""
        SELECT
            LENGTH('{safe_canon}')                  AS L,
            HEX_ENCODE('{safe_canon}')              AS HEX,   -- uppercase hex
            HASH('{safe_canon}')                    AS H
    """).collect()[0]
    char_len = int(meta_row['L'])
    hex_utf8 = str(meta_row['HEX'])
    hash64   = int(meta_row['H'])

    # 3) Show debug (so you can see the trailing space and exact bytes)
    st.write(f"Ingredients (canonical): {repr(canonical_ingredients)}")
    st.write(f"UTF-8 HEX (from Snowflake): {hex_utf8}")
    st.write(f"Char LEN (from Snowflake): {char_len}")
    st.write(f"Snowflake HASH() (64-bit): {hash64}")

    # 4) Nutrition info from API (uses SEARCH_ON singulars)
    for fruit_label in ingredients_list:
        row_match = pd_df.loc[pd_df["FRUIT_NAME"] == fruit_label, "SEARCH_ON"]
        search_on = str(row_match.iloc[0]) if not row_match.empty else fruit_label
        st.subheader(f"{fruit_label} Nutrition Information")
        try:
            response = requests.get(f"https://my.smoothiefroot.com/api/fruit/{search_on}")
            if response.ok:
                st.dataframe(response.json(), use_container_width=True)
            else:
                st.warning(f"Could not fetch info for '{fruit_label}' (as '{search_on}'). Status: {response.status_code}")
        except Exception as e:
            st.error(f"Error fetching data for '{fruit_label}': {e}")

    # 5) Prepare safe values for INSERT
    safe_name    = (name_on_order or "").replace("'", "''")
    safe_display = display_ingredients.replace("'", "''")

    if STORE_CANON_IN_INGREDIENTS:
        # Put the canonical value (with trailing space) into INGREDIENTS as well
        safe_ing = safe_canon
    else:
        # Keep UI value in INGREDIENTS, canonical goes to INGREDIENTS_CANON
        safe_ing = safe_display

    insert_sql = f"""
        INSERT INTO smoothies.public.orders
            (INGREDIENTS, INGREDIENTS_CANON, NAME_ON_ORDER, HEX_UTF8, LEN, HASH64)
        VALUES
            ('{safe_ing}', '{safe_canon}', '{safe_name}', '{hex_utf8}', {char_len}, {hash64})
    """

    if st.button("Submit Order"):
        try:
            session.sql(insert_sql).collect()
            st.success("Your Smoothie is ordered!", icon="✅")

            # Optional: immediately show what was just written (last inserted row by name)
            st.info("Row written to Snowflake (verification):")
            verify_df = session.sql(f"""
                SELECT
                    NAME_ON_ORDER,
                    INGREDIENTS,
                    INGREDIENTS_CANON,
                    LEN,
                    HEX_UTF8,
                    HASH64
                FROM smoothies.public.orders
                WHERE NAME_ON_ORDER = '{safe_name}'
                ORDER BY 1 DESC, 2 DESC
                LIMIT 1
            """).to_pandas()
            st.dataframe(verify_df, use_container_width=True)

        except Exception as e:
            st.error(f"Order submission failed: {e}")






