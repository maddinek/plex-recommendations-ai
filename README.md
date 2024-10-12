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
   ```sh
   git clone https://github.com/yourusername/plex-ai-recommendations.git
   cd plex-ai-recommendations
   ```

2. Install required packages:
   ```sh
   pip install -r requirements.txt
   ```

3. Create a `config` directory and add a `plex_recommendations.ini` file with the following content:
   ```ini
   [PLEX]
   PLEX_URL = http://your-plex-server:32400
   PLEX_TOKEN = your-plex-token

   [GPT]
   GPT4O_API_KEY = your-gpt4o-api-key

   [OMBI]
   OMBI_URL = http://your-ombi-server:3579
   OMBI_API_KEY = your-ombi-api-key
   ```

   Replace the placeholder values with your actual Plex, GPT-4o, and Ombi (if using) credentials.

4. Create an `output` directory to store generated recommendation files.

## Usage

Run the script:
```sh
python plex-recommendations.py
```

The script will:

1. Retrieve your watch history from Plex
2. Generate recommendations for movies and TV shows
3. Create or update collections in Plex
4. Add missing titles to Ombi (if configured)
5. Save recommendations to CSV files in the output directory

## Configuration

You can modify the `additional_collections` list in the `main()` function to add or remove themed collections.

## Running with Docker

You can also run the application using Docker. Here are the steps:

1. Build the Docker image:
   ```sh
   podman-compose build
   ```

2. Start the container:
   ```sh
   podman-compose up
   ```

This will create and run the container, mounting the necessary `config` and `output` directories.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
