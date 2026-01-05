
# Import python packages
import streamlit as st
from snowflake.snowpark.functions import col

# --- Get a Snowflake Snowpark session using Streamlit's connection API ---
# This uses your [connections.snowflake] block from secrets.toml
conn = st.connection("snowflake", type="snowflake")
session = conn.session()

# ---- UI ----
st.title(":cup_with_straw: Customize Your Smoothie! :cup_with_straw:")
st.write("Choose the fruits you want in your custom Smoothie!")

# Name input
name_on_order = st.text_input("Name on Smoothie:")
st.write("The name on your Smoothie will be:", name_on_order)

# ---- Load Fruit Options from Snowflake ----
fruit_df = (
    session.table("SMOOTHIES.PUBLIC.FRUIT_OPTIONS")
    .select(col("FRUIT_NAME"))
    .sort(col("FRUIT_NAME"))
)

# Convert Snowpark rows -> Python list
fruit_list = [row[0] for row in fruit_df.collect()]

# ---- Ingredient Selector ----
ingredients_list = st.multiselect(
    "Choose up to 5 ingredients:",
    fruit_list,
    max_selections=5
)

# ---- Submit Button ----
if ingredients_list:
    ingredients_string = " ".join(ingredients_list)

    # Prevent SQL injection by escaping single quotes
    safe_ingredients = ingredients_string.replace("'", "''")
    safe_name = name_on_order.strip().replace("'", "''")

    insert_sql = f"""
        INSERT INTO SMOOTHIES.PUBLIC.ORDERS (INGREDIENTS, NAME_ON_ORDER)
        VALUES ('{safe_ingredients}', '{safe_name}')
    """

    submit = st.button(
        "Submit Order",
        disabled=not name_on_order,
        help="Enter your name above." if not name_on_order else None
    )

    if submit:
        session.sql(insert_sql).collect()
        st.success("Your Smoothie is ordered!", icon="✅")

        st.write(f"**Ingredients:** {ingredients_string}")
        st.write(f"**Name:** {name_on_order}")

