# Plex AI Recommendations

This script generates personalized movie and TV show recommendations based on your Plex watch history, creates collections in Plex, and adds missing titles to Ombi for requesting.

## Features

- Retrieves your watch history from Plex
- Generates personalized recommendations using GPT-4o mini API
- Creates and updates collections in Plex based on recommendations
- Adds missing titles to Ombi for requesting
- Supports various themed collections (e.g., Seasonal, Holiday, Romantic Comedy)
- Saves recommendations to CSV files

## Prerequisites

- Python 3.9+
- Plex Media Server
- Ombi (optional, for requesting missing titles)
- GPT-4o mini API access

## Installation

1. Clone this repository:
git clone https://github.com/yourusername/plex-ai-recommendations.git
cd plex-ai-recommendations

2. Install required packages:
pip install -r requirements.txt

3. Create a `plex_recommendations.ini` file in the project root with the following content:
```ini
[PLEX]
PLEX_URL = http://your-plex-server:32400
PLEX_TOKEN = your-plex-token

[GPT]
GPT4O_API_KEY = your-gpt4o-api-key

[OMBI]
OMBI_URL = http://your-ombi-server:3579
OMBI_API_KEY = your-ombi-api-key

Replace the placeholder values with your actual Plex, GPT-4o, and Ombi (if using) credentials.
Usage
Run the script:
python plex-recommendations.py

The script will:

1. Retrieve your watch history from Plex
2. Generate recommendations for movies and TV shows
3. Create or update collections in Plex
4. Add missing titles to Ombi (if configured)
5. Save recommendations to CSV files in the output directory

Configuration
You can modify the additional_collections list in the main() function to add or remove themed collections.
Contributing
Contributions are welcome! Please feel free to submit a Pull Request.
License
This project is licensed under the MIT License - see the LICENSE file for details.

This README provides an overview of your project, its features, installation instructions, usage guide, and other relevant information. You may want to adjust some details (like the repository URL) to match your specific setup. Also, consider adding a LICENSE file to your repository if you haven't already.
