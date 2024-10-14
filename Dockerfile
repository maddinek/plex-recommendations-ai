# Use an official Python runtime as the base image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install required packages
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the current directory contents into the container at /app
COPY plex-recommendations.py /app/
COPY requirements.txt /app/
RUN ls -l /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Create a directory for configurations
RUN mkdir /config

# Create a directory for output files
RUN mkdir /output

# Set environment variable for the config file location
ENV CONFIG_FILE=/config/plex_recommendations.ini

# Run plex-recommendations.py when the container launches
CMD ["python", "plex-recommendations.py"]

