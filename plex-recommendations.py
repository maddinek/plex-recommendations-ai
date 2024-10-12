import os
import requests
import json
import pandas as pd
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, BadRequest
from plexapi.video import Movie, Show
from plexapi.library import MovieSection, ShowSection
import time
import configparser
from datetime import datetime
from requests.exceptions import RequestException, Timeout

def read_config(config_file=None):
    """Read configuration from the specified file or environment variable."""
    if config_file is None:
        config_file = os.environ.get('CONFIG_FILE', 'plex_recommendations.ini')
    config = configparser.ConfigParser()
    config.read(config_file)
    return config

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

def get_recommendations(prompt, media_type):
    """Get recommendations from GPT-4o mini API."""
    config = read_config()
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

def add_to_ombi(missing_titles, collection_name):
    """Add missing titles to Ombi for requesting."""
    config = read_config()
    try:
        OMBI_URL = config.get('OMBI', 'OMBI_URL')
        OMBI_API_KEY = config.get('OMBI', 'OMBI_API_KEY')
    except (configparser.NoSectionError, configparser.NoOptionError):
        print(f"Ombi configuration not found or incomplete. Skipping Ombi integration for {collection_name}.")
        return

    if not OMBI_URL or not OMBI_API_KEY:
        print(f"Ombi URL or API key is empty. Skipping Ombi integration for {collection_name}.")
        return

    headers = {
        'ApiKey': OMBI_API_KEY,
        'Content-Type': 'application/json'
    }

    timeout = 30

    if missing_titles:
        print(f"Adding missing titles from {collection_name} to Ombi:")
        for title in missing_titles:
            try:
                search_url = f"{OMBI_URL}/api/v1/Search/multi/{title}"
                search_response = requests.get(search_url, headers=headers, timeout=timeout)
                
                if search_response.status_code == 200:
                    search_results = search_response.json()
                    if search_results:
                        media_result = next((item for item in search_results if item['type'] in ['movie', 'tv']), None)
                        
                        if media_result:
                            media_type = media_result['type']
                            if media_type == 'movie':
                                request_url = f"{OMBI_URL}/api/v1/Request/movie"
                                request_data = {
                                    'theMovieDbId': media_result['id'],
                                    'languageCode': 'en'
                                }
                            else:  # TV show
                                request_url = f"{OMBI_URL}/api/v1/Request/tv"
                                request_data = {
                                    'tvDbId': media_result['id'],
                                    'requestAll': True,
                                    'languageCode': 'en'
                                }
                            
                            request_response = requests.post(request_url, headers=headers, json=request_data, timeout=timeout)
                            
                            if request_response.status_code == 200:
                                print(f"  - Successfully added to Ombi: {title}")
                            else:
                                print(f"  - Failed to add to Ombi: {title}. Status code: {request_response.status_code}")
                        else:
                            print(f"  - Could not find matching media type for: {title}")
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
    else:
        print(f"No missing titles to add to Ombi for {collection_name}.")

def main():
    start_time = time.time()
    
    config = read_config()
    PLEX_URL = config.get('PLEX', 'PLEX_URL')
    PLEX_TOKEN = config.get('PLEX', 'PLEX_TOKEN')
    
    if not PLEX_URL or not PLEX_TOKEN:
        print("Error: PLEX_URL and/or PLEX_TOKEN not found in configuration file.")
        return

    try:
        plex = PlexServer(PLEX_URL, PLEX_TOKEN)
    except Exception as e:
        print(f"An error occurred while connecting to Plex: {e}")
        return

    watched_titles = get_watched_titles(plex)
    if not watched_titles:
        print("No watched titles found in your Plex library.")
        return

    updated_collections = []

    # Standard recommendations for Movies and TV Shows
    for media_type in ['Movie', 'TV Show']:
        prompt = f"""
        I have watched the following movies and TV shows:

        {', '.join(watched_titles)}

        Based on this list, recommend 10 new {media_type.lower()}s that I might like. For each recommendation, provide the following in JSON format:

        {{
          "title": "Title of the {media_type.lower()}",
          "genre": "Genre(s)",
          "description": "A brief description"
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
                if isinstance(rec, dict) and all(key in rec for key in ('title', 'genre', 'description'))
            ]
            if valid_recommendations:
                recommendations_df = pd.DataFrame(valid_recommendations)
                collection_name = f'AI Recommended {media_type}s'
                missing_titles = create_collection_with_recommendations(plex, recommendations_df, media_type, collection_name)
                add_to_ombi(missing_titles, collection_name)
                output_file = f'/output/{media_type.lower()}_recommendations.csv'
                recommendations_df.to_csv(output_file, index=False)
                print(f"\n{media_type} recommendations saved to '{output_file}'.")
                updated_collections.append(collection_name)
            else:
                print(f"No valid {media_type.lower()} recommendations were found.")
        except Exception as e:
            print(f"An error occurred while processing {media_type.lower()} recommendations: {e}")

    # Additional collections for Movies
    additional_collections = [
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
    ]

    for collection_name, recommendation_prompt in additional_collections:
        prompt = f"""
        Based on the following criteria:

        {recommendation_prompt}

        For each recommendation, provide the following in JSON format:

        {{
          "title": "Title of the movie",
          "genre": "Genre(s)",
          "description": "A brief description"
        }}

        Please provide the entire response as a JSON array of objects.
        """

        try:
            print(f"Requesting recommendations for {collection_name} collection...")
            response = get_recommendations(prompt, "Movie")
            recommendations_text = response['choices'][0]['message']['content'].strip()
            recommendations = parse_recommendations(recommendations_text)
            valid_recommendations = [
                rec for rec in recommendations 
                if isinstance(rec, dict) and all(key in rec for key in ('title', 'genre', 'description'))
            ]
            if valid_recommendations:
                recommendations_df = pd.DataFrame(valid_recommendations)
                missing_titles = create_collection_with_recommendations(plex, recommendations_df, "Movie", collection_name)
                add_to_ombi(missing_titles, collection_name)
                output_file = f'/output/{collection_name.lower().replace(" ", "_")}_recommendations.csv'
                recommendations_df.to_csv(output_file, index=False)
                print(f"\n{collection_name} recommendations saved to '{output_file}'.")
                updated_collections.append(collection_name)
            else:
                print(f"No valid recommendations were found for {collection_name} collection.")
        except Exception as e:
            print(f"An error occurred while processing {collection_name} recommendations: {e}")

    print("\nUpdated collections:")
    for collection in updated_collections:
        print(f"- {collection}")

if __name__ == "__main__":
    main()
