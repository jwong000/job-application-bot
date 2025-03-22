# Job Application Bot

An automated tool for streamlining the job application process across multiple platforms including LinkedIn, Indeed, and Glassdoor.

## Overview

This script automates searching and applying for jobs based on customizable criteria. It can:

1. Log into multiple job platforms
2. Search for jobs matching your keywords and locations
3. Filter out jobs with undesired keywords
4. Automatically fill application forms
5. Track application statistics
6. Generate reports on your job application activity
7. Send email summaries with insights on in-demand skills

## Disclaimer

**Important:** This tool is provided for educational purposes only. Using automated bots to interact with websites may violate their Terms of Service. Many job platforms actively detect and block automation tools, and your account could be suspended for using them. Consider using this tool as a learning resource or modifying it to assist your job search rather than fully automating it.

## Requirements

- Python 3.6+
- Chrome/Chromium browser
- Stable internet connection
- Valid accounts on job platforms (LinkedIn, Indeed, Glassdoor)

## Installation

1. Clone or download this repository
2. Install the required dependencies:

```bash
pip install selenium webdriver-manager beautifulsoup4 requests
```

3. Place your resume in PDF format in the project directory

## Configuration

Edit the `config` dictionary in the `main()` function:

```python
config = {
    "email": "your.email@example.com",  # Replace with your email
    "resume_path": "resume.pdf",  # Path to your resume file
    "keywords": [
        "software engineer", 
        "python developer", 
        "entry level developer", 
        "junior developer",
        "graduate developer",
        "software developer",
        "embedded engineer"
    ],
    "locations": [
        "Remote", 
        "San Francisco, CA", 
        "New York, NY", 
        "Seattle, WA",
        "Austin, TX"
    ],
    "exclude_keywords": [
        "senior", 
        "lead", 
        "manager", 
        "director", 
        "principal",
        "staff",
        "10+ years",
        "5+ years"
    ],
    "headless": False,  # Set to True for background operation
    "max_applications": 10  # Maximum applications per run
}
```

For the email report functionality, update the SMTP settings in the `send_email_report()` method:

```python
smtp_server = "smtp.gmail.com"  # Replace with your SMTP server
smtp_port = 587
smtp_username = self.email  # Replace with SMTP username if different
smtp_password = "your_app_password"  # Replace with app password or actual password
```

## Usage

Run the script with:

```bash
python job_application_bot.py
```

The script will:
1. Initialize the browser and authenticate with job platforms
2. Search for jobs matching your criteria
3. Filter out unwanted jobs
4. Apply to jobs up to your maximum limit
5. Generate a report and send an email summary

## Features

### Automated Form Filling

The bot automatically fills common form fields including:
- Name (first/last)
- Email address
- Phone number
- Resume upload
- Work experience
- Education level
- Yes/No qualification questions

### Human-like Interaction

To reduce detection risk:
- Typing speed varies naturally
- Random delays between actions
- Mimics normal user navigation patterns

### Complex Application Detection

The bot identifies and skips applications requiring:
- Long-form text answers
- External website redirects
- Custom questions beyond simple forms

### Reporting and Analysis

After each run, the bot:
- Saves a JSON report of all activity
- Generates statistics on application success/failure
- Analyzes most common skills requested in job descriptions
- Sends an HTML email summary with insights

## Customization

### Skill Analysis

The bot analyzes job descriptions for in-demand skills. You can customize the skills list in the `_analyze_skill_requirements()` method.

### Application Behavior

Modify the `_fill_linkedin_form()`, `_fill_indeed_form()`, and `_fill_glassdoor_form()` methods to change how the bot interacts with application forms.

## Troubleshooting

Common issues:
- **Authentication failures**: Check your login credentials and ensure you can manually log in
- **CAPTCHA detection**: The script attempts to handle CAPTCHAs but may fail with advanced ones
- **Browser crashes**: Try updating Chrome or your webdriver
- **Email sending errors**: Verify SMTP settings and ensure less secure app access is enabled for your email

## Contributing

Contributions are welcome! Some areas for improvement:
- Support for additional job platforms
- Enhanced CAPTCHA solving
- Improved form detection
- Machine learning for smarter job filtering
- Cover letter generation

## License

This project is provided as-is for educational purposes.
