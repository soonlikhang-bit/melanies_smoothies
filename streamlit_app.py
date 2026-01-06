# Import python packages
import streamlit as st
import requests
from snowflake.snowpark.functions import col

# Write directly to the app
st.title(f":cup_with_straw: Customize Your Smoothie! :cup_with_straw:")
st.write("Choose the fruits you want in your custom Smoothie!")

name_on_order = st.text_input('Name on Smoothie:')
st.write('The name on your Smoothie will be:', name_on_order)

cnx = st.connection("snowflake")
session = cnx.session()

# 1. Ensure SEARCH_ON column is set up with correct values
setup_sql = """
ALTER TABLE smoothies.public.fruit_options ADD COLUMN IF NOT EXISTS SEARCH_ON STRING;
UPDATE smoothies.public.fruit_options SET SEARCH_ON = FRUIT_NAME WHERE SEARCH_ON IS NULL;
UPDATE smoothies.public.fruit_options SET SEARCH_ON = 'Apples' WHERE FRUIT_NAME = 'Apple';
UPDATE smoothies.public.fruit_options SET SEARCH_ON = 'Blueberries' WHERE FRUIT_NAME = 'Blueberry';
UPDATE smoothies.public.fruit_options SET SEARCH_ON = 'Jack Fruit' WHERE FRUIT_NAME = 'Jackfruit';
UPDATE smoothies.public.fruit_options SET SEARCH_ON = 'Raspberries' WHERE FRUIT_NAME = 'Raspberry';
UPDATE smoothies.public.fruit_options SET SEARCH_ON = 'Strawberries' WHERE FRUIT_NAME = 'Strawberry';
"""
session.sql(setup_sql).collect()  # Run setup on each start (safe & idempotent)

# 2. Load fruit names and SEARCH_ON for display and API use
my_dataframe = session.table("smoothies.public.fruit_options").select(
    col('FRUIT_NAME'), col('SEARCH_ON')
).to_pandas()

ingredients_list = st.multiselect(
    'Choose up to 5 ingredients:',
    my_dataframe['FRUIT_NAME'],
    max_selections=5
)

if ingredients_list:
    ingredients_string = ''
    for fruit_chosen in ingredients_list:
        ingredients_string += fruit_chosen + ' '
        # Use SEARCH_ON for API call
        search_on_value = my_dataframe.loc[
            my_dataframe['FRUIT_NAME'] == fruit_chosen, 'SEARCH_ON'
        ].values[0]
        st.subheader(f"{fruit_chosen} Nutrition Information")
        smoothiefroot_response = requests.get(
            "https://my.smoothiefroot.com/api/fruit/" + search_on_value
        )
        st.dataframe(data=smoothiefroot_response.json(), use_container_width=True)

    my_insert_stmt = f"""
    INSERT INTO smoothies.public.orders (INGREDIENTS, NAME_ON_ORDER)
    VALUES ('{ingredients_string}', '{name_on_order}')
    """

    time_to_insert = st.button('Submit Order')
    if time_to_insert:
        session.sql(my_insert_stmt).collect()
        st.success('Your Smoothie is ordered!', icon="✅")






