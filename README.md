# Scholarship Tracker

This Python application automatically fetches scholarship updates for bachelor's and master's programs from trusted websites and sends daily email updates using Gemini AI for intelligent processing.

## Setup Instructions

1. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Configure the environment variables in `.env` file:
   ```
   GOOGLE_API_KEY=your_gemini_api_key
   EMAIL_ADDRESS=your_gmail_address
   EMAIL_PASSWORD=your_gmail_app_password
   RECIPIENT_EMAIL=recipient_email_address
   ```

3. Gmail Setup:
   - Enable 2-factor authentication
   - Generate an App Password for this application

4. Update the following variables in `scholarship_tracker.py`:
   - `GOOGLE_API_KEY`: Your Gemini API key
   - `EMAIL_ADDRESS`: Your Gmail address
   - `EMAIL_PASSWORD`: Your Gmail app-specific password
   - `RECIPIENT_EMAIL`: Email address to receive updates

## Features

- Daily scholarship updates from trusted sources
- AI-powered processing using Google's Gemini
- Structured email updates with detailed information
- Automatic scheduling of daily updates
- Error logging for monitoring

## Running the Application

```
python scholarship_tracker.py
```


## Logging

All activities and errors are logged in `scholarship_tracker.log`
