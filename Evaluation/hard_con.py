from utils.func import get_valid_name_city, extract_before_parenthesis, extract_numbers_from_filenames
from tools.flights.apis import Flights
from tools.bus.apis import Buses
from tools.train.apis import Trains
from tools.accommodations.apis import Accommodations
from tools.restaurants.apis import Restaurants
from tools.googleDistanceMatrix.apis import GoogleDistanceMatrix
from tools.attractions.apis import Attractions
from tools.events.apis import Events
import math
import json
import re
import numpy as np
import os
import sys
from tqdm import tqdm
import argparse

sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "..")))
os.chdir(os.path.dirname(os.path.abspath(__file__)))


flight = Flights()
bus = Buses()
train = Trains()
accommodation = Accommodations()
restaurants = Restaurants()
googleDistanceMatrix = GoogleDistanceMatrix()
attractions = Attractions()
events = Events()


def load_line_json_data(filename):
    data = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f.read().strip().split('\n'):
            unit = json.loads(line)
            data.append(unit)
    return data


def convert_bool_values(item):
    if isinstance(item, dict):
        return {key: convert_bool_values(value) for key, value in item.items()}
    elif isinstance(item, list):
        return [convert_bool_values(value) for value in item]
    elif isinstance(item, tuple):
        return tuple(convert_bool_values(value) for value in item)
    elif isinstance(item, np.bool_):
        return bool(item)
    else:
        return item


def extract_from_to(text: str):
    """
    Extracts 'A' and 'B' from the format "from A to B" in the given text,
    with B ending at a comma or the end of the string.

    Args:
    - text (str): The input string.

    Returns:
    - tuple: A tuple containing 'A' and 'B'. If no match is found, returns (None, None).
    """
    pattern = r"from\s+(.+?)\s+to\s+([^,]+)(?=[,\s]|$)"
    matches = re.search(pattern, text)
    return matches.groups() if matches else (None, None)


def get_total_cost(question, tested_data):
    total_cost = 0
    days = question.get('days', len(tested_data))
    people = question.get('people_number', 1)
    for i in range(min(days, len(tested_data))):
        unit = tested_data[i]

        # transportation
        if unit['transportation'] and unit['transportation'] != '-':
            value = unit['transportation']
            org_city, dest_city = extract_from_to(value)
            if org_city is None or dest_city is None:
                org_city, dest_city = extract_from_to(unit['current_city'])

            if org_city is None or dest_city is None:
                pass
            else:
                if 'flight number' in value.lower():
                    res = flight.data[flight.data['Flight Number'] == value.split('Flight Number: ')[1].split(',')[0]]
                    if len(res) > 0:
                        total_cost += res['Price'].values[0] * people

                elif 'cab' in value.lower() or 'taxi' in value.lower():
                    cost = googleDistanceMatrix.run_for_evaluation(org_city, dest_city, 'taxi')['cost']
                    total_cost += cost * math.ceil(people * 1.0 / 4)

                elif 'bus' in value.lower():
                    try:
                        operator = value.split('Bus Operator: ')[1].split(',')[0].strip()
                        res = bus.data[bus.data['operator'] == operator]
                        if len(res) > 0:
                            price_str = str(res['price'].values[0]).replace('₹', '').replace(',', '').strip()
                            total_cost += float(price_str) * people
                    except:
                        pass

                elif 'train' in value.lower():
                    try:
                        # Train Number: 
                        train_no = value.split('Train Number: ')[1].split(' ')[0].strip()
                        res = train.data[train.data['train_no'].astype(str) == str(train_no)]
                        if len(res) > 0:
                            total_cost += float(res['calculated_fare'].values[0]) * people
                    except:
                        pass

        # breakfast
        if unit['breakfast'] and unit['breakfast'] != '-':
            name, city = get_valid_name_city(unit['breakfast'])
            res = restaurants.data[(restaurants.data['name'].astype(str).str.contains(re.escape(name))) & (restaurants.data['City'] == city)]
            if len(res) > 0:
                total_cost += res['avg_cost'].values[0] * question['people_number']

        # lunch
        if unit['lunch'] and unit['lunch'] != '-':
            name, city = get_valid_name_city(unit['lunch'])
            res = restaurants.data[(restaurants.data['name'].astype(str).str.contains(re.escape(name))) & (restaurants.data['City'] == city)]
            if len(res) > 0:
                total_cost += res['avg_cost'].values[0] * question['people_number']

        # dinner
        if unit['dinner'] and unit['dinner'] != '-':
            name, city = get_valid_name_city(unit['dinner'])
            res = restaurants.data[(restaurants.data['name'].astype(str).str.contains(re.escape(name))) & (restaurants.data['City'] == city)]
            if len(res) > 0:
                total_cost += res['avg_cost'].values[0] * people

        # accommodation
        if unit['accommodation'] and unit['accommodation'] != '-':
            name, city = get_valid_name_city(unit['accommodation'])
            res = accommodation.data[(accommodation.data['name'].astype(str).str.contains(re.escape(name))) & (accommodation.data['City'] == city)]
            if len(res) > 0:
                pricing_data = res['pricing'].values[0]
                if isinstance(pricing_data, str):
                    try:
                        pricing_data = json.loads(pricing_data)
                    except json.JSONDecodeError:
                        pricing_data = {}
                price_str = pricing_data.get('price', '').replace('$', '').strip()
                if price_str:
                    price = float(price_str)
                    max_occupancy = res['max_occupancy'].values[0]
                    total_cost += price * math.ceil(people / max_occupancy)

    return total_cost


def is_valid_room_rule(question, tested_data):

    rule = question.get('local_constraint', {}).get('house_rules')
    if rule is None:
        return None, None

    # Mapping from user-facing rule names to your dataset's house rule values
    RULE_MAP = {
        'smoking':              'No_Smoking',
        'children':             'No_Children',
        'children under 10':    'No_Children',
        'pets':                 'No_Pets',
        'checkin':              'Checkin_Checkout',
        'checkout':             'Checkin_Checkout',
        'checkin checkout':     'Checkin_Checkout',
        'safety':               'Safety_Conduct',
        'safety conduct':       'Safety_Conduct',
    }

    rule_key = RULE_MAP.get(rule.lower())
    if rule_key is None:
        return None, None  # Unknown rule, skip validation

    days = question.get('days', len(tested_data))
    for i in range(min(days, len(tested_data))):
        unit = tested_data[i]
        if unit['accommodation'] and unit['accommodation'] != '-':
            name, city = get_valid_name_city(unit['accommodation'])
            res = accommodation.data[
                (accommodation.data['name'].astype(str).str.contains(re.escape(name))) &
                (accommodation.data['City'] == city)
            ]
            if len(res) > 0:
                house_rules_str = str(res['house_rules'].values[0])

                # Check if the required rule is NOT present in the accommodation's house rules
                if rule_key not in house_rules_str:
                    return False, f"The house rule '{rule_key}' is required but not found in the accommodation's house rules."

    return True, None


def is_valid_cuisine(question, tested_data):
    cuisine_set = set()
    cuisines = question.get('local_constraint', {}).get('cuisine')
    if cuisines:
        for i in range(min(question.get('days', len(tested_data)), len(tested_data))):
            unit = tested_data[i]

            if unit['breakfast'] and unit['breakfast'] != '-':
                name, city = get_valid_name_city(unit['breakfast'])
                if city == question['org']:
                    continue
                res = restaurants.data[(restaurants.data['name'].astype(str).str.contains(re.escape(name))) & (restaurants.data['City'] == city)]
                if len(res) > 0:
                    for cuisine in cuisines:
                        if cuisine in res.iloc[0]['cuisines']:
                            cuisine_set.add(cuisine)

            if unit['lunch'] and unit['lunch'] != '-':
                name, city = get_valid_name_city(unit['lunch'])
                if city == question['org']:
                    continue
                res = restaurants.data[(restaurants.data['name'].astype(str).str.contains(re.escape(name))) & (restaurants.data['City'] == city)]
                if len(res) > 0:
                    for cuisine in cuisines:
                        if cuisine in res.iloc[0]['cuisines']:
                            cuisine_set.add(cuisine)

            if unit['dinner'] and unit['dinner'] != '-':
                name, city = get_valid_name_city(unit['dinner'])
                if city == question['org']:
                    continue
                res = restaurants.data[(restaurants.data['name'].astype(str).str.contains(re.escape(name))) & (restaurants.data['City'] == city)]
                if len(res) > 0:
                    if cuisines:
                        for cuisine in cuisines:
                            if cuisine in res.iloc[0]['cuisines']:
                                cuisine_set.add(cuisine)

        if cuisines and len(cuisine_set) == len(cuisines):
            return True, None
        else:
            if cuisines:
                for cuisine in cuisines:
                    if cuisine not in cuisine_set:
                        return False, f"The cuisine {cuisine} is not satisfied."
    else:
        return None, None


def is_valid_attraction_type(question, tested_data):
    attraction_set = set()

    attractions_req = question.get('local_constraint', {}).get('attraction')
    if attractions_req:
        attraction_types = attractions_req
        if isinstance(attraction_types, str):
            attraction_types = [attraction_types]

        days = question.get('days', len(tested_data))
        for i in range(min(days, len(tested_data))):
            unit = tested_data[i]

            if unit['attraction'] and unit['attraction'] != '-':
                attraction_list = unit['attraction'].split(';')
                for attraction in attraction_list:
                    name, city = get_valid_name_city(attraction)
                    if city == question['org']:
                        continue

                    res = attractions.data[(attractions.data['name'].astype(str).str.contains(re.escape(name))) & (attractions.data['City'] == city)]

                    if len(res) > 0:
                        for attraction_type in attraction_types:
                            if attraction_type in res.iloc[0]['subcategories']:
                                attraction_set.add(attraction_type)

        if len(attraction_set) == len(attraction_types):
            return True, None
        else:
            for attraction_type in attraction_types:
                if attraction_type not in attraction_set:
                    return False, f"The attraction type {attraction_type} is not satisfied."
    else:
        return None, None


def is_valid_event_type(question, tested_data):
    event_set = set()

    events_req = question.get('local_constraint', {}).get('event')
    if events_req:
        event_types = events_req
        if isinstance(event_types, str):
            event_types = [event_types]

        days = question.get('days', len(tested_data))
        for i in range(min(days, len(tested_data))):
            unit = tested_data[i]

            if unit['event'] and unit['event'] != '-':
                event_list = unit['event'].split(';')
                for event in event_list:
                    name = event.rsplit(',', 1)[0].strip()
                    city = event.rsplit(',', 1)[-1].strip()
                    dates = question.get('date')
                    if not dates:
                        continue
                    event_data = events.run(city, dates)

                    res = event_data[(event_data['name'].astype(str).str.contains(re.escape(name)))]

                    if len(res) > 0:
                        for event_type in event_types:
                            if event_type == res.iloc[0]['segmentName']:
                                event_set.add(event_type)

        if len(event_set) == len(event_types):
            return True, None
        else:
            for event_type in event_types:
                if event_type not in event_set:
                    return False, f"The event type {event_type} is not satisfied."
    else:
        return None, None


def is_valid_transportation(question, tested_data):
    trans_req = question.get('local_constraint', {}).get('transportation')
    if trans_req is None:
        return None, None

    days = question.get('days', len(tested_data))
    for i in range(min(days, len(tested_data))):
        unit = tested_data[i]
        if unit['transportation'] and unit['transportation'] != '-':
            value = unit['transportation']
            value_l = value.lower()

            if trans_req == 'no flight' and 'flight' in value_l:
                return False, f"The transportation should not be {trans_req}."
            elif trans_req == 'no cab' and ('cab' in value_l or 'taxi' in value_l):
                return False, f"The transportation should not be {trans_req}."

    return True, None


def is_valid_room_type(question, tested_data):
    room_type_val = question.get('local_constraint', {}).get('house_type')
    if room_type_val is None:
        return None, None

    # Mapping from user-facing room type names to your dataset's HOUSE_TYPE values
    ROOM_TYPE_MAP = {
        'apartment extended':   'Apartment_Extended',
        'apartment':            'Apartment_Extended',
        'business':             'Business',
        'family friendly':      'Family_Friendly',
        'family':               'Family_Friendly',
        'luxury boutique':      'Luxury_Boutique',
        'luxury':               'Luxury_Boutique',
        'boutique':             'Luxury_Boutique',
        'resort beach':         'Resort_Beach',
        'resort':               'Resort_Beach',
        'beach':                'Resort_Beach',
    }

    room_type_key = ROOM_TYPE_MAP.get(room_type_val.lower())
    if room_type_key is None:
        return None, None  # Unknown room type, skip validation

    days = question.get('days', len(tested_data))
    for i in range(min(days, len(tested_data))):
        unit = tested_data[i]
        if unit['accommodation'] and unit['accommodation'] != '-':
            name, city = get_valid_name_city(unit['accommodation'])
            res = accommodation.data[
                (accommodation.data['name'].astype(str).str.contains(re.escape(name))) &
                (accommodation.data['City'] == city)
            ]
            if len(res) > 0:
                house_type_str = str(res['HOUSE_TYPE'].values[0])

                if room_type_key not in house_type_str:
                    return False, f"The room type should be {room_type_key}, but not found in accommodation's house types."

    return True, None


def evaluation(query_data, tested_data):
    return_info = {}
    return_info['valid_cuisine'] = is_valid_cuisine(query_data, tested_data)
    return_info['valid_room_rule'] = is_valid_room_rule(query_data, tested_data)
    return_info['valid_transportation'] = is_valid_transportation(query_data, tested_data)
    return_info['valid_room_type'] = is_valid_room_type(query_data, tested_data)
    return_info['valid_attraction_type'] = is_valid_attraction_type(query_data, tested_data)
    return_info['valid_event_type'] = is_valid_event_type(query_data, tested_data)
    return_info['valid_cost'] = (bool(get_total_cost(query_data, tested_data) <= query_data.get('budget', 0)), None)
    return return_info


def boolean_evaluation(query_data, tested_data):
    return_info = {}
    return_info['valid_cuisine'] = is_valid_cuisine(query_data, tested_data)
    return_info['valid_room_rule'] = is_valid_room_rule(query_data, tested_data)
    return_info['valid_transportation'] = is_valid_transportation(query_data, tested_data)
    return_info['valid_room_type'] = is_valid_room_type(query_data, tested_data)
    return_info['valid_attraction_type'] = is_valid_attraction_type(query_data, tested_data)
    return_info['valid_event_type'] = is_valid_event_type(query_data, tested_data)
    return_info['valid_cost'] = (bool(get_total_cost(query_data, tested_data) <= query_data['budget']), None)
    for key in return_info:
        if return_info[key][0] is False:
            print(key)
            return False
    return True
