
# Import python packages
import streamlit as st
import requests
from snowflake.snowpark.functions import col

# Write directly to the app
st.title(":cup_with_straw: Customize Your Smoothie! :cup_with_straw:")
st.write("Choose the fruits you want in your custom Smoothie!")

# Gather name for the order
name_on_order = st.text_input('Name on Smoothie:')
st.write('The name on your Smoothie will be:', name_on_order)

# Snowflake connection
cnx = st.connection("snowflake")
session = cnx.session()

# ---- Pull display name and API search name from FRUIT_OPTIONS ----
# We select both FRUIT_NAME (human-friendly) and SEARCH_ON (API key)
fruits_df = (
    session.table("smoothies.public.fruit_options")
           .select(col('FRUIT_NAME'), col('SEARCH_ON'))
           .sort(col('FRUIT_NAME'))
)

# Prepare a list for the UI and a mapping for API calls
fruit_display_list = [row['FRUIT_NAME'] for row in fruits_df.collect()]
fruit_to_searchon = {row['FRUIT_NAME']: row['SEARCH_ON'] for row in fruits_df.collect()}

# Ingredient selector
ingredients_list = st.multiselect(
    'Choose up to 5 ingredients:',
    fruit_display_list,
    max_selections=5
)

# ---- When the user has chosen ingredients ----
if ingredients_list:

    # Build a readable string for storage (what the user saw/selected)
    ingredients_string = " ".join(ingredients_list).strip()

    # Show nutrition for each chosen fruit using the API spelling in SEARCH_ON
    for fruit_chosen in ingredients_list:
        # Map the UI label to the API name; fallback to the same string if missing
        api_name = fruit_to_searchon.get(fruit_chosen, fruit_chosen)

        st.subheader(f"{fruit_chosen} • Nutrition Information")

        # Basic network call with simple error handling
        try:
            resp = requests.get(f"https://my.smoothiefroot.com/api/fruit/{api_name}", timeout=10)
            resp.raise_for_status()
            st.dataframe(data=resp.json(), use_container_width=True)
        except Exception as e:
            st.error(f"Could not load nutrition for '{fruit_chosen}' (API name: '{api_name}'). Error: {e}")

    # Compose INSERT statement
    my_insert_stmt = f"""
    INSERT INTO smoothies.public.orders (INGREDIENTS, NAME_ON_ORDER)
    VALUES ('{ingredients_string}', '{name_on_order}')
    """

    # Submit button
    time_to_insert = st.button('Submit Order')

    # Execute the insert when clicked
    if time_to_insert:
        session.sql(my_insert_stmt).collect()
        st.success('Your Smoothie is ordered!', icon="✅")




