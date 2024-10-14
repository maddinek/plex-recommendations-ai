import os
import requests
import json
import pandas as pd
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, BadRequest
import time
import configparser
from datetime import datetime
from requests.exceptions import RequestException, Timeout

# import logging
# logging.basicConfig(level=logging.DEBUG)

def read_config(config_file=None):
    """Read configuration from the specified file or environment variable."""
    if config_file is None:
        config_file = os.environ.get('CONFIG_FILE', 'plex_recommendations.ini')
    config = configparser.ConfigParser()
    config.read(config_file)
    return config, config_file

def check_ombi_credentials(config):
    """Check if Ombi credentials are set in the config."""
    try:
        ombi_url = config.get('OMBI', 'OMBI_URL')
        ombi_api_key = config.get('OMBI', 'OMBI_API_KEY')
        return bool(ombi_url and ombi_api_key)
    except (configparser.NoSectionError, configparser.NoOptionError):
        return False

def get_watched_titles(plex):
    """Retrieve watched movies and TV shows from Plex."""
    print("Retrieving watched movies and TV shows from Plex...")
    watched_titles = []

    movies = plex.library.section('Movies').all()
    watched_titles.extend([movie.title for movie in movies if movie.isPlayed])

    tv_shows = plex.library.section('TV Shows').all()
    for show in tv_shows:
        if show.isWatched or any(episode.isPlayed for episode in show.episodes()):
            watched_titles.append(show.title)

    watched_titles = list(set(watched_titles))
    print(f"Total watched titles retrieved: {len(watched_titles)}")
    return watched_titles

def get_user_preferences(plex):
    """Retrieve user's ratings for movies and TV shows from Plex."""
    ratings = {}

    print("Retrieving user ratings from Plex...")

    # Get ratings from Movies
    for movie in plex.library.section('Movies').all():
        if hasattr(movie, 'userRating') and movie.userRating is not None:
            ratings[movie.title] = movie.userRating

    # Get ratings from TV Shows
    tv_shows = plex.library.section('TV Shows').all()  # This line was missing, so now it's added
    for show in tv_shows:
        if hasattr(show, 'userRating') and show.userRating is not None:
            ratings[show.title] = show.userRating

    print(f"Found {len(ratings)} rated titles.")
    return ratings

def get_recommendations(prompt, media_type):
    """Get recommendations from GPT-4o mini API."""
    config, _ = read_config()
    API_KEY = config.get('GPT', 'GPT4O_API_KEY')

    if not API_KEY:
        raise Exception("GPT4O_API_KEY not found in configuration file.")

    url = 'https://api.openai.com/v1/chat/completions'

    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json',
    }

    data = {
        'model': 'gpt-4o-mini',
        'messages': [
            {"role": "system", "content": f"You are a recommendation system for {media_type}s."},
            {"role": "user", "content": prompt}
        ],
        'max_tokens': 10000,
        'temperature': 0.7,
        'n': 1,
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}: {response.text}")

    return response.json()

def parse_recommendations(response_text):
    """Parse the API response and extract recommendations."""
    try:
        recommendations = json.loads(response_text)
        return recommendations
    except json.JSONDecodeError:
        json_start = response_text.find('[')
        json_end = response_text.rfind(']')
        if json_start != -1 and json_end != -1:
            try:
                recommendations = json.loads(response_text[json_start:json_end+1])
                return recommendations
            except json.JSONDecodeError:
                pass
        raise Exception("Failed to parse the response as JSON.")

def get_current_season():
    """Determine the current season based on the current month."""
    month = datetime.now().month
    if 3 <= month <= 5:
        return "Spring"
    elif 6 <= month <= 8:
        return "Summer"
    elif 9 <= month <= 11:
        return "Fall"
    else:
        return "Winter"

def get_upcoming_holiday():
    """Determine the upcoming holiday based on the current date."""
    now = datetime.now()
    if now.month == 10:
        return "Halloween"
    elif now.month == 12:
        return "Christmas"
    elif now.month == 11:
        return "Thanksgiving"
    elif now.month == 2 and now.day <= 14:
        return "Valentine's Day"
    else:
        return None

def create_collection_with_recommendations(plex, recommendations_df, media_type, collection_name):
    """Create or update a Plex collection with recommended items and feature it on the home screen."""
    plex_items = []
    missing_titles = []

    section = plex.library.section('Movies' if media_type == 'Movie' else 'TV Shows')

    for _, row in recommendations_df.iterrows():
        title = row['title']
        try:
            results = section.search(title)
            found = False
            for result in results:
                if result.title.lower() == title.lower():
                    plex_items.append(result)
                    found = True
                    print(f"Found in Plex: {title}")
                    result.addLabel(f"AI Recommended - {collection_name}")
                    print(f"Added 'AI Recommended - {collection_name}' tag to: {title}")
                    break
            if not found:
                missing_titles.append(title)
                print(f"Not found in Plex: {title}")
        except NotFound:
            missing_titles.append(title)
            print(f"Not found in Plex: {title}")
            continue

    if plex_items:
        try:
            collection = section.collection(collection_name)
            print(f"Existing collection found: {collection_name}")
            collection.addItems(plex_items)
            print(f"Added {len(plex_items)} items to existing collection")
        except NotFound:
            try:
                print(f"Creating new collection: {collection_name}")
                collection = section.createCollection(title=collection_name, items=plex_items)
                print(f"Created new collection with {len(plex_items)} items")
            except BadRequest as e:
                print(f"Error creating collection: {e}")
                return missing_titles

        # Update collection summary with reasons
        summary = "Recommendations based on your watch history, favorites, and ratings:\n\n"
        for _, row in recommendations_df.iterrows():
            if row['title'] in [item.title for item in plex_items]:
                summary += f"- {row['title']}: {row['reason']}\n"
        collection.editSummary(summary)

        # Feature the collection on the home screen
        try:
            collection.edit(**{"smart": 0, "promote": 1})
            print(f"Collection '{collection_name}' featured on the home screen.")
        except Exception as e:
            print(f"Error featuring collection on home screen: {e}")

        print(f"Collection '{collection_name}' updated with {len(plex_items)} items.")
    else:
        print(f"No recommended items found in your Plex library for {collection_name}. Skipping collection creation.")

    if missing_titles:
        print(f"\nRecommended items not found in your Plex library for {collection_name}:")
        for title in missing_titles:
            print(f"- {title}")

    return missing_titles

def add_to_ombi(missing_titles, collection_name, config):
    """Add missing titles to Ombi for requesting."""
    OMBI_URL = config.get('OMBI', 'OMBI_URL')
    OMBI_API_KEY = config.get('OMBI', 'OMBI_API_KEY')

    print(f"Adding missing titles from {collection_name} to Ombi:")

    headers = {
        'ApiKey': OMBI_API_KEY,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    timeout = 30

    for title in missing_titles:
        try:
            if 'movie' in collection_name.lower():
                search_url = f"{OMBI_URL}/api/v1/Search/movie/{title}"
            else:
                search_url = f"{OMBI_URL}/api/v1/Search/tv/{title}"

            search_response = requests.get(search_url, headers=headers, timeout=timeout)

            if search_response.status_code == 200:
                search_results = search_response.json()
                if search_results:
                    media_result = search_results[0]
                    media_type = 'movie' if 'movie' in collection_name.lower() else 'tv'

                    if media_type == 'movie':
                        request_url = f"{OMBI_URL}/api/v1/Request/movie"
                        request_data = {
                            'theMovieDbId': media_result['theMovieDbId'],
                            'languageCode': 'en'
                        }
                    else:
                        request_url = f"{OMBI_URL}/api/v1/Request/tv"
                        request_data = {
                            'tvDbId': media_result['theTvDbId'],
                            'requestAll': True,
                            'languageCode': 'en'
                        }

                    request_response = requests.post(request_url, headers=headers, json=request_data, timeout=timeout)

                    if request_response.status_code == 200:
                        print(f"  - Successfully added to Ombi: {title}")
                    else:
                        print(f"  - Failed to add to Ombi: {title}. Status code: {request_response.status_code}")
                else:
                    print(f"  - Could not find in Ombi database: {title}")
            else:
                print(f"  - Failed to search in Ombi: {title}. Status code: {search_response.status_code}")
        except Timeout:
            print(f"  - Timeout occurred while processing: {title}. The request took longer than {timeout} seconds to complete.")
        except RequestException as e:
            print(f"  - An error occurred while processing: {title}. Error: {str(e)}")

        time.sleep(1)  # Add a small delay between requests

    print(f"Finished processing Ombi additions for {collection_name}.")

# Trakt functionality starts here
def request_device_code(client_id):
    """Request a device code from Trakt."""
    url = "https://api.trakt.tv/oauth/device/code"
    headers = {'Content-Type': 'application/json'}
    payload = {
        'client_id': client_id
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        return response.json()  # Contains device_code, user_code, verification_url, expires_in, interval
    else:
        raise Exception(f"Failed to request device code: {response.status_code}, {response.text}")

def poll_for_access_token(device_code, client_id, client_secret, interval):
    """Poll for the access token using the device code."""
    url = "https://api.trakt.tv/oauth/device/token"
    headers = {'Content-Type': 'application/json'}
    payload = {
        'code': device_code,
        'client_id': client_id,
        'client_secret': client_secret
    }

    while True:
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            return response.json()  # Contains access_token, refresh_token, expires_in
        elif response.status_code == 400:
            print("Authorization pending...")
        elif response.status_code == 404:
            print("Invalid device code.")
            break
        elif response.status_code == 409:
            print("Device code already used.")
            break
        elif response.status_code == 410:
            print("Device code expired.")
            break
        elif response.status_code == 418:
            print("Authorization denied.")
            break

        time.sleep(interval)  # Wait for the specified interval before polling again

def get_trakt_access_token(config, config_file):
    """Get or refresh Trakt access token using the Device Flow."""
    client_id = config.get('TRAKT', 'CLIENT_ID')
    client_secret = config.get('TRAKT', 'CLIENT_SECRET')
    access_token = config.get('TRAKT', 'ACCESS_TOKEN', fallback=None)
    refresh_token = config.get('TRAKT', 'REFRESH_TOKEN', fallback=None)
    token_expiry_str = config.get('TRAKT', 'TOKEN_EXPIRY', fallback='0')

    try:
        token_expiry = int(token_expiry_str)
    except ValueError:
        token_expiry = 0

    if access_token and int(time.time()) < token_expiry:
        return access_token

    if refresh_token:
        # Try to refresh the token
        token_url = "https://api.trakt.tv/oauth/token"
        data = {
            'refresh_token': refresh_token,
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'refresh_token'
        }
        response = requests.post(token_url, json=data)

        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data['access_token']
            refresh_token = token_data['refresh_token']
            expires_in = token_data['expires_in']

            config.set('TRAKT', 'ACCESS_TOKEN', access_token)
            config.set('TRAKT', 'REFRESH_TOKEN', refresh_token)
            config.set('TRAKT', 'TOKEN_EXPIRY', str(int(time.time()) + expires_in))

            # Writing back to the config file
            with open(config_file, 'w') as configfile:
                config.write(configfile)

            return access_token

    # Use Device Flow if no tokens are present
    device_data = request_device_code(client_id)

    print(f"Go to {device_data['verification_url']} and enter the code: {device_data['user_code']}")

    # Poll for the access token
    token_data = poll_for_access_token(
        device_data['device_code'],
        client_id,
        client_secret,
        device_data['interval']
    )

    if token_data:
        access_token = token_data['access_token']
        refresh_token = token_data['refresh_token']
        expires_in = token_data['expires_in']

        # Save tokens in the config file
        config.set('TRAKT', 'ACCESS_TOKEN', access_token)
        config.set('TRAKT', 'REFRESH_TOKEN', refresh_token)
        config.set('TRAKT', 'TOKEN_EXPIRY', str(int(time.time()) + expires_in))

        # Writing back to the config file
        with open(config_file, 'w') as configfile:
            config.write(configfile)

        return access_token
    else:
        print("Failed to obtain access token.")
        return None

def check_trakt_credentials(config, config_file):
    """Check if Trakt credentials are set in the config and obtain/refresh access token if needed."""
    try:
        client_id = config.get('TRAKT', 'CLIENT_ID')
        client_secret = config.get('TRAKT', 'CLIENT_SECRET')

        if not client_id or not client_secret:
            print("Trakt CLIENT_ID or CLIENT_SECRET is missing in the configuration file.")
            return False

        access_token = get_trakt_access_token(config, config_file)
        return bool(access_token)
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        print(f"Error in Trakt configuration: {e}")
        return False

def add_to_trakt(missing_titles, collection_name, config):
    """Add missing titles to a Trakt collection."""
    trakt_url = "https://api.trakt.tv/sync/collection"
    access_token = config.get('TRAKT', 'ACCESS_TOKEN')

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': config.get('TRAKT', 'CLIENT_ID')
    }

    print(f"Adding missing titles from {collection_name} to Trakt:")

    for title in missing_titles:
        # Construct data for each movie or show
        media_data = {
            "movies": [{"title": title}] if 'movie' in collection_name.lower() else None,
            "shows": [{"title": title}] if 'tv' in collection_name.lower() else None
        }

        # Remove empty entries
        media_data = {k: v for k, v in media_data.items() if v is not None}

        try:
            response = requests.post(trakt_url, headers=headers, json=media_data)
            if response.status_code == 201:
                print(f"  - Successfully added to Trakt: {title}")
            else:
                print(f"  - Failed to add to Trakt: {title}. Status code: {response.status_code}")
        except RequestException as e:
            print(f"  - An error occurred while processing: {title}. Error: {str(e)}")

        time.sleep(1)  # Add a small delay between requests

    print(f"Finished processing Trakt additions for {collection_name}.")

def main():
    start_time = time.time()

    config, config_file = read_config()
    PLEX_URL = config.get('PLEX', 'PLEX_URL')
    PLEX_TOKEN = config.get('PLEX', 'PLEX_TOKEN')
    NUMBER_OF_RECOMMENDATIONS = config.getint('RECOMMENDATIONS', 'NUMBER_OF_RECOMMENDATIONS', fallback=10)

    if not PLEX_URL or not PLEX_TOKEN:
        print("Error: PLEX_URL and/or PLEX_TOKEN not found in configuration file.")
        return

    ombi_enabled = check_ombi_credentials(config)
    if ombi_enabled:
        print("Ombi credentials found. Ombi integration will be used.")
    else:
        print("Ombi credentials not found or incomplete. Ombi integration will be skipped.")

    trakt_enabled = check_trakt_credentials(config, config_file)
    if trakt_enabled:
        print("Trakt credentials found. Trakt integration will be used.")
    else:
        print("Trakt credentials not found or incomplete. Trakt integration will be skipped.")

    try:
        plex = PlexServer(PLEX_URL, PLEX_TOKEN)
    except Exception as e:
        print(f"An error occurred while connecting to Plex: {e}")
        return

    watched_titles = get_watched_titles(plex)
    ratings = get_user_preferences(plex)

    if not watched_titles and not ratings:
        print("No watched titles or ratings found in your Plex library.")
        return

    updated_collections = []

    # Standard recommendations for Movies and TV Shows
    for media_type in ['Movie', 'TV Show']:
        prompt = f"""
        I have watched the following movies and TV shows:

        {', '.join(watched_titles)}

        I have rated the following titles (out of 10):
        {', '.join([f"{title} ({rating})" for title, rating in ratings.items()])}

        Based on this information, recommend {NUMBER_OF_RECOMMENDATIONS} new {media_type.lower()}s that I might like. For each recommendation, provide the following in JSON format:

        {{
          "title": "Title of the {media_type.lower()}",
          "genre": "Genre(s)",
          "description": "A brief description",
          "reason": "A brief explanation of why this is recommended based on my watch history and ratings"
        }}

        Please provide the entire response as a JSON array of objects.
        """

        try:
            print(f"Requesting {media_type} recommendations from the GPT-4o mini API...")
            response = get_recommendations(prompt, media_type)
            recommendations_text = response['choices'][0]['message']['content'].strip()
            recommendations = parse_recommendations(recommendations_text)
            valid_recommendations = [
                rec for rec in recommendations
                if isinstance(rec, dict) and all(key in rec for key in ('title', 'genre', 'description', 'reason'))
            ]
            if valid_recommendations:
                recommendations_df = pd.DataFrame(valid_recommendations)
                collection_name = f'AI Recommended {media_type}s'
                missing_titles = create_collection_with_recommendations(plex, recommendations_df, media_type, collection_name)
                if ombi_enabled:
                    add_to_ombi(missing_titles, collection_name, config)
                if trakt_enabled:
                    add_to_trakt(missing_titles, collection_name, config)

                output_file = f'/output/{media_type.lower()}_recommendations.csv'
                recommendations_df.to_csv(output_file, index=False)
                print(f"\n{media_type} recommendations saved to '{output_file}'.")
                updated_collections.append(collection_name)
            else:
                print(f"No valid {media_type.lower()} recommendations were found.")
        except Exception as e:
            print(f"An error occurred while processing {media_type.lower()} recommendations: {e}")

    # Additional collections for Movies and TV Shows
    additional_collections = {
        'Movie': [
            ("Seasonal", f"Recommend 10 movies suitable for {get_current_season()} season."),
            ("Holiday", f"Recommend 10 movies suitable for {get_upcoming_holiday() or 'the upcoming holiday season'}."),
            ("Romantic Comedy", "Recommend 10 top romantic comedy movies."),
            ("Action Adventure", "Recommend 10 exciting action-adventure movies."),
            ("Family Friendly", "Recommend 10 family-friendly movies suitable for all ages."),
            ("Sci-Fi Spectacle", "Recommend 10 mind-bending science fiction movies."),
            ("Classic Cinema", "Recommend 10 classic movies from various decades that have stood the test of time."),
            ("Based on True Story", "Recommend 10 compelling movies based on true stories or real events."),
            ("90s & 00s Teenage Movies", "Recommend 10 iconic teenage movies from the 1990s and 2000s."),
            ("Very Sarcastic Movies", "Recommend 10 highly sarcastic or satirical movies, similar in tone to 'Baby Mama (2008)' or 'They Came Together (2014)'.")
        ],
        'TV Show': [
            ("Seasonal", f"Recommend 10 TV shows suitable for {get_current_season()} season."),
            ("Holiday", f"Recommend 10 TV shows suitable for {get_upcoming_holiday() or 'the upcoming holiday season'}."),
            ("Romantic Comedy", "Recommend 10 top romantic comedy TV shows."),
            ("Family Friendly", "Recommend 10 family-friendly TV shows suitable for all ages."),
            ("Sci-Fi Spectacle", "Recommend 10 mind-bending science fiction TV shows."),
            ("Classic TV Shows", "Recommend 10 classic TV shows from various decades that have stood the test of time."),
            ("Based on True Story", "Recommend 10 compelling TV shows based on true stories or real events.")
        ]
    }

    for media_type, collections in additional_collections.items():
        for collection_name, recommendation_prompt in collections:
            prompt = f"""
            Based on the following criteria:

            {recommendation_prompt}

            For each recommendation, provide the following in JSON format:

            {{
              "title": "Title of the {media_type.lower()}",
              "genre": "Genre(s)",
              "description": "A brief description",
              "reason": "A brief explanation of why this {media_type.lower()} fits the criteria"
            }}

            Please provide the entire response as a JSON array of objects.
            """

            try:
                print(f"Requesting recommendations for {collection_name} {media_type.lower()} collection...")
                response = get_recommendations(prompt, media_type)
                recommendations_text = response['choices'][0]['message']['content'].strip()
                recommendations = parse_recommendations(recommendations_text)
                valid_recommendations = [
                    rec for rec in recommendations
                    if isinstance(rec, dict) and all(key in rec for key in ('title', 'genre', 'description', 'reason'))
                ]
                if valid_recommendations:
                    recommendations_df = pd.DataFrame(valid_recommendations)
                    missing_titles = create_collection_with_recommendations(plex, recommendations_df, media_type, collection_name)
                    if trakt_enabled:
                        add_to_trakt(missing_titles, collection_name, config)
                    if ombi_enabled:
                        add_to_ombi(missing_titles, collection_name, config)

                    output_file = f'/output/{collection_name.lower().replace(" ", "_")}_{media_type.lower()}_recommendations.csv'
                    recommendations_df.to_csv(output_file, index=False)
                    print(f"\n{collection_name} {media_type.lower()} recommendations saved to '{output_file}'.")
                    updated_collections.append(f"{collection_name} ({media_type})")
                else:
                    print(f"No valid recommendations were found for {collection_name} {media_type.lower()} collection.")
            except Exception as e:
                print(f"An error occurred while processing {collection_name} {media_type.lower()} recommendations: {e}")

    print("\nUpdated collections:")
    for collection in updated_collections:
        print(f"- {collection}")

    end_time = time.time()
    print(f"\nTotal execution time: {end_time - start_time:.2f} seconds")

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
