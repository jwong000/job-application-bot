import requests
import time
import smtplib
import os
import json
import re
import random
import logging
import base64
import pickle
import threading
from bs4 import BeautifulSoup
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from fake_useragent import UserAgent
from cryptography.fernet import Fernet

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("job_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("JobBot")

class CredentialManager:
    """Handles secure storage and retrieval of credentials"""
    
    def __init__(self, key_file="encryption_key.key"):
        self.key_file = key_file
        self.key = self._load_or_generate_key()
        self.cipher = Fernet(self.key)
        
    def _load_or_generate_key(self):
        """Load existing key or generate a new one"""
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(key)
            return key
    
    def save_credentials(self, platform, username, password):
        """Encrypt and save credentials"""
        credentials = {
            "username": username,
            "password": password
        }
        encrypted_data = self.cipher.encrypt(json.dumps(credentials).encode())
        
        if not os.path.exists("credentials"):
            os.makedirs("credentials")
            
        with open(f"credentials/{platform}.enc", "wb") as f:
            f.write(encrypted_data)
            
    def get_credentials(self, platform):
        """Retrieve and decrypt credentials"""
        try:
            with open(f"credentials/{platform}.enc", "rb") as f:
                encrypted_data = f.read()
                
            decrypted_data = self.cipher.decrypt(encrypted_data)
            credentials = json.loads(decrypted_data.decode())
            return credentials["username"], credentials["password"]
            
        except FileNotFoundError:
            logger.error(f"No credentials found for {platform}")
            return None, None
        except Exception as e:
            logger.error(f"Error retrieving credentials for {platform}: {str(e)}")
            return None, None

class BrowserManager:
    """Manages browser session with anti-detection measures"""
    
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = None
        
    def start_browser(self):
        """Initialize and configure browser with anti-detection measures"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
        
        # Anti-bot detection settings
        user_agent = UserAgent().random
        chrome_options.add_argument(f'--user-agent={user_agent}')
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--no-sandbox")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Further anti-detection measures
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": user_agent})
        
        # Set reasonable cookies and local storage to appear like a returning user
        self.driver.execute_script("localStorage.setItem('returning_visitor', 'true');")
        
        return self.driver
    
    def close_browser(self):
        """Close browser safely"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def save_cookies(self, platform):
        """Save cookies for a platform"""
        if not self.driver:
            logger.error("Browser not initialized")
            return
            
        if not os.path.exists("cookies"):
            os.makedirs("cookies")
            
        pickle.dump(self.driver.get_cookies(), 
                   open(f"cookies/{platform}.pkl", "wb"))
    
    def load_cookies(self, platform):
        """Load cookies for a platform"""
        if not self.driver:
            logger.error("Browser not initialized")
            return
            
        try:
            cookies = pickle.load(open(f"cookies/{platform}.pkl", "rb"))
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            return True
        except Exception as e:
            logger.error(f"Error loading cookies for {platform}: {str(e)}")
            return False

class AuthenticationManager:
    """Handles authentication for different job platforms"""
    
    def __init__(self, credential_manager, browser_manager):
        self.credential_manager = credential_manager
        self.browser_manager = browser_manager
        self.auth_status = {
            "linkedin": False,
            "indeed": False,
            "glassdoor": False
        }
    
    def authenticate(self, platform):
        """Authenticate with a specific platform"""
        username, password = self.credential_manager.get_credentials(platform)
        
        if not username or not password:
            logger.error(f"Missing credentials for {platform}")
            return False
        
        driver = self.browser_manager.driver
        
        # Platform-specific login processes
        if platform == "linkedin":
            try:
                # Navigate to login page
                driver.get("https://www.linkedin.com/login")
                
                # Check if cookies can be used
                if self.browser_manager.load_cookies(platform):
                    driver.get("https://www.linkedin.com/feed/")
                    if "feed" in driver.current_url:
                        self.auth_status[platform] = True
                        logger.info("LinkedIn authenticated with cookies")
                        return True
                
                # If cookies don't work, login manually
                username_field = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "username"))
                )
                password_field = driver.find_element(By.ID, "password")
                
                # Add natural typing behavior
                self._natural_type(username_field, username)
                self._natural_type(password_field, password)
                
                # Submit login form
                driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                
                # Wait for successful login
                WebDriverWait(driver, 15).until(
                    lambda d: "feed" in d.current_url
                )
                
                # Save cookies for future use
                self.browser_manager.save_cookies(platform)
                self.auth_status[platform] = True
                logger.info("LinkedIn authentication successful")
                return True
                
            except Exception as e:
                logger.error(f"LinkedIn authentication failed: {str(e)}")
                return False
                
        elif platform == "indeed":
            try:
                driver.get("https://secure.indeed.com/account/login")
                
                # Check if cookies can be used
                if self.browser_manager.load_cookies(platform):
                    driver.get("https://www.indeed.com/")
                    # Check for sign-in element to verify if we're logged in
                    try:
                        sign_in = driver.find_element(By.CSS_SELECTOR, "[data-gnav-element-name='SignIn']")
                        # If sign-in element exists, we're not logged in
                    except NoSuchElementException:
                        self.auth_status[platform] = True
                        logger.info("Indeed authenticated with cookies")
                        return True
                
                # Login with email first
                email_field = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "ifl-InputFormField-3"))
                )
                self._natural_type(email_field, username)
                
                # Click continue
                driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                
                # Now enter password
                password_field = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "ifl-InputFormField-7"))
                )
                self._natural_type(password_field, password)
                
                # Submit password
                driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                
                # Wait for successful login
                WebDriverWait(driver, 15).until(
                    lambda d: "captcha" not in d.current_url and "login" not in d.current_url
                )
                
                # Save cookies for future use
                self.browser_manager.save_cookies(platform)
                self.auth_status[platform] = True
                logger.info("Indeed authentication successful")
                return True
                
            except Exception as e:
                logger.error(f"Indeed authentication failed: {str(e)}")
                return False
                
        elif platform == "glassdoor":
            try:
                driver.get("https://www.glassdoor.com/profile/login_input.htm")
                
                # Check if cookies can be used
                if self.browser_manager.load_cookies(platform):
                    driver.get("https://www.glassdoor.com/member/home/index.htm")
                    if "home" in driver.current_url:
                        self.auth_status[platform] = True
                        logger.info("Glassdoor authenticated with cookies")
                        return True
                
                # Sometimes Glassdoor shows email field first, sometimes both
                try:
                    # Try email-first approach
                    email_field = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.ID, "modalUserEmail"))
                    )
                    self._natural_type(email_field, username)
                    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                    
                    # Then enter password
                    password_field = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.ID, "modalUserPassword"))
                    )
                    self._natural_type(password_field, password)
                    
                except TimeoutException:
                    # Try combined approach
                    email_field = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.ID, "username"))
                    )
                    password_field = driver.find_element(By.ID, "password")
                    
                    self._natural_type(email_field, username)
                    self._natural_type(password_field, password)
                
                # Submit login
                driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                
                # Wait for successful login
                WebDriverWait(driver, 15).until(
                    lambda d: "member" in d.current_url
                )
                
                # Save cookies for future use
                self.browser_manager.save_cookies(platform)
                self.auth_status[platform] = True
                logger.info("Glassdoor authentication successful")
                return True
                
            except Exception as e:
                logger.error(f"Glassdoor authentication failed: {str(e)}")
                return False
        
        return False
    
    def _natural_type(self, element, text):
        """Type text in a human-like manner with variable speed"""
        for char in text:
            element.send_keys(char)
            # Random delay between keystrokes (30-100ms)
            time.sleep(random.uniform(0.03, 0.1))

class CaptchaSolver:
    """Simple captcha detection and handling"""
    
    def __init__(self, driver):
        self.driver = driver
        
    def detect_captcha(self):
        """Detect various types of captchas"""
        # Check for common captcha indicators
        captcha_indicators = [
            # reCAPTCHA 
            "//iframe[contains(@src, 'recaptcha')]",
            "//div[contains(@class, 'recaptcha')]",
            # hCaptcha
            "//iframe[contains(@src, 'hcaptcha')]",
            # Text indicators
            "//*[contains(text(), 'captcha') or contains(text(), 'Captcha')]",
            "//*[contains(text(), 'robot') or contains(text(), 'Robot')]",
            "//*[contains(text(), 'human') or contains(text(), 'Human')]",
        ]
        
        for xpath in captcha_indicators:
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
                if elements:
                    return True
            except:
                pass
                
        return False
    
    def handle_captcha(self):
        """Handle detected captcha"""
        if self.detect_captcha():
            logger.warning("Captcha detected! Pausing for human intervention.")
            
            # Alert the user
            print("\n" + "="*50)
            print("⚠️ CAPTCHA DETECTED - Human Intervention Required ⚠️")
            print(f"Please solve the captcha in the browser window.")
            print("The program will continue after you solve it.")
            print("="*50 + "\n")
            
            # Wait for user to solve the captcha (maximum 5 minutes)
            timeout = time.time() + 300  # 5 minutes
            while time.time() < timeout:
                if not self.detect_captcha():
                    logger.info("Captcha appears to be solved.")
                    time.sleep(2)  # Give a moment for page to process
                    return True
                time.sleep(3)
            
            logger.error("Captcha not solved within timeout period.")
            return False
        
        return True

class JobApplicationBot:
    """Main bot class for searching and applying to jobs"""
    
    def __init__(self, email, resume_path, keywords, locations, exclude_keywords=None, headless=False):
        self.email = email
        self.resume_path = os.path.abspath(resume_path)
        self.keywords = keywords
        self.locations = locations
        self.exclude_keywords = exclude_keywords or []
        self.applied_jobs = self._load_applied_jobs()
        self.job_boards = {
            "linkedin": {
                "search_url": "https://www.linkedin.com/jobs/search/",
                "params": {"keywords": "", "location": "", "f_E": "1,2", "sortBy": "DD"}
            },
            "indeed": {
                "search_url": "https://www.indeed.com/jobs",
                "params": {"q": "", "l": "", "fromage": "7", "sort": "date"}
            },
            "glassdoor": {
                "search_url": "https://www.glassdoor.com/Job/jobs.htm",
                "params": {"sc.keyword": "", "locT": "C", "locId": 0}
            }
        }
        
        # Initialize managers
        self.credential_manager = CredentialManager()
        self.browser_manager = BrowserManager(headless=headless)
        self.auth_manager = AuthenticationManager(self.credential_manager, self.browser_manager)
        self.driver = None
        self.captcha_solver = None
        
        # Resume text for matching
        self.resume_text = self._extract_resume_text()
        
        # Stats tracking
        self.stats = {
            "jobs_found": 0,
            "jobs_filtered": 0,
            "applications_attempted": 0,
            "applications_completed": 0,
            "applications_failed": 0
        }
    
    def _extract_resume_text(self):
        """Extract text from resume for matching purposes"""
        # For PDF resume
        try:
            import PyPDF2
            with open(self.resume_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text.lower()
        except Exception as e:
            logger.error(f"Error extracting text from resume: {str(e)}")
            logger.warning("Using basic resume text extraction. Install PyPDF2 for better results.")
            # Fallback to provided resume text
            return """computer engineer python java c++ software developer embedded systems
                      mathematics physics flask arduino machine learning sql mysql database
                      raspberrypi linux github digital systems data structures algorithms
                      vlsi transistors circuits microcontroller programming entry level new grad"""
    
    def _load_applied_jobs(self):
        """Load previously applied jobs from JSON file"""
        if os.path.exists('applied_jobs.json'):
            with open('applied_jobs.json', 'r') as f:
                return json.load(f)
        return []
    
    def _save_applied_jobs(self):
        """Save applied jobs to JSON file"""
        with open('applied_jobs.json', 'w') as f:
            json.dump(self.applied_jobs, f)
    
    def initialize(self):
        """Initialize browser and authenticate with job platforms"""
        self.driver = self.browser_manager.start_browser()
        self.captcha_solver = CaptchaSolver(self.driver)
        
        # Store authentication results
        auth_results = {}
        
        for platform in self.job_boards.keys():
            auth_success = self.auth_manager.authenticate(platform)
            auth_results[platform] = auth_success
            
            if not auth_success:
                logger.warning(f"Authentication failed for {platform}. Some features might be limited.")
            
        # Return authentication status
        return auth_results
    
    def search_jobs(self, days=7):
        """Search for jobs across multiple job boards"""
        all_jobs = []
        
        for board_name, board_info in self.job_boards.items():
            # Skip platforms we couldn't authenticate with
            if not self.auth_manager.auth_status[board_name]:
                logger.warning(f"Skipping job search on {board_name} due to authentication failure")
                continue
                
            logger.info(f"Searching jobs on {board_name}...")
            
            for keyword in self.keywords:
                for location in self.locations:
                    try:
                        jobs = self._search_platform(board_name, keyword, location)
                        all_jobs.extend(jobs)
                        
                        # Randomized delay between searches (3-7 seconds)
                        time.sleep(random.uniform(3, 7))
                        
                    except Exception as e:
                        logger.error(f"Error searching {board_name} for {keyword} in {location}: {str(e)}")
        
        self.stats["jobs_found"] = len(all_jobs)
        
        # Filter jobs
        filtered_jobs = self._filter_jobs(all_jobs)
        self.stats["jobs_filtered"] = len(filtered_jobs)
        
        logger.info(f"Found {len(all_jobs)} jobs, filtered to {len(filtered_jobs)} relevant positions")
        return filtered_jobs
    
    def _search_platform(self, platform, keyword, location):
        """Search for jobs on a specific platform"""
        jobs = []
        
        if platform == "linkedin":
            # Build search URL with parameters
            params = self.job_boards[platform]["params"].copy()
            params["keywords"] = keyword
            params["location"] = location
            
            # Construct query string
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            search_url = f"{self.job_boards[platform]['search_url']}?{query_string}"
            
            # Navigate to search page
            self.driver.get(search_url)
            
            # Wait for results to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-search__results-list"))
            )
            
            # Handle "Show more jobs" button if present to load more results
            try:
                show_more = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.infinite-scroller__show-more-button"))
                )
                show_more.click()
                time.sleep(2)  # Wait for more jobs to load
            except:
                pass
            
            # Parse job listings
            job_cards = self.driver.find_elements(By.CSS_SELECTOR, ".job-search-card")
            
            for card in job_cards:
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, ".job-search-card__title")
                    company_elem = card.find_element(By.CSS_SELECTOR, ".job-search-card__subtitle")
                    link_elem = card.find_element(By.CSS_SELECTOR, "a.job-search-card__link")
                    
                    job = {
                        'title': title_elem.text.strip(),
                        'company': company_elem.text.strip(),
                        'url': link_elem.get_attribute('href'),
                        'source': 'linkedin',
                        'date_found': datetime.now().strftime('%Y-%m-%d'),
                        'keywords': [keyword],
                        'location': location
                    }
                    
                    # Try to get job description
                    try:
                        # Click on job to see details
                        title_elem.click()
                        
                        # Wait for description to load
                        description_elem = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".job-details-jobs-unified-description__content"))
                        )
                        
                        job['description'] = description_elem.text
                    except:
                        job['description'] = ""
                    
                    jobs.append(job)
                    
                except Exception as e:
                    logger.error(f"Error parsing LinkedIn job card: {str(e)}")
        
        elif platform == "indeed":
            # Similar implementation for Indeed
            params = self.job_boards[platform]["params"].copy()
            params["q"] = keyword
            params["l"] = location
            
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            search_url = f"{self.job_boards[platform]['search_url']}?{query_string}"
            
            self.driver.get(search_url)
            
            # Wait for results
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".jobsearch-ResultsList"))
            )
            
            # Parse job cards
            job_cards = self.driver.find_elements(By.CSS_SELECTOR, ".job_seen_beacon")
            
            for card in job_cards:
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, "h2.jobTitle")
                    company_elem = card.find_element(By.CSS_SELECTOR, "span.companyName")
                    
                    # Get job link
                    link_elem = title_elem.find_element(By.TAG_NAME, "a")
                    job_url = link_elem.get_attribute("href")
                    
                    job = {
                        'title': title_elem.text.strip(),
                        'company': company_elem.text.strip(),
                        'url': job_url,
                        'source': 'indeed',
                        'date_found': datetime.now().strftime('%Y-%m-%d'),
                        'keywords': [keyword],
                        'location': location
                    }
                    
                    # Try to get description
                    try:
                        link_elem.click()
                        description_elem = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.ID, "jobDescriptionText"))
                        )
                        job['description'] = description_elem.text
                    except:
                        job['description'] = ""
                    
                    jobs.append(job)
                    
                except Exception as e:
                    logger.error(f"Error parsing Indeed job card: {str(e)}")
        
        elif platform == "glassdoor":
            # Glassdoor implementation
            params = self.job_boards[platform]["params"].copy()
            params["sc.keyword"] = keyword
            
            # Glassdoor uses location IDs, simplified here
            search_url = f"{self.job_boards[platform]['search_url']}?{params['sc.keyword']}={keyword}"
            
            self.driver.get(search_url)
            
            # Wait for results
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".react-job-listing"))
            )
            
            # Close any popups
            try:
                close_button = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".modal_closeIcon"))
                )
                close_button.click()
            except:
                pass
            
            # Parse job listings
            job_cards = self.driver.find_elements(By.CSS_SELECTOR, ".react-job-listing")
            
            for card in job_cards:
                try:
                    card.click()  # Click to load details
                    time.sleep(1)
                    
                    # Get job details
                    title_elem = card.find_element(By.CSS_SELECTOR, "a.jobLink")
                    company_elem = card.find_element(By.CSS_SELECTOR, ".css-1nqghjk")
                    
                    # Get job link
                    job_url = title_elem.get_attribute("href")
                    
                    job = {
                        'title': title_elem.text.strip(),
                        'company': company_elem.text.strip(),
                        'url': job_url,
                        'source': 'glassdoor',
                        'date_found': datetime.now().strftime('%Y-%m-%d'),
                        'keywords': [keyword],
                        'location': location
                    }
                    
                    # Try to get description
                    try:
                        description_elem = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".jobDescriptionContent"))
                        )
                        job['description'] = description_elem.text
                    except:
                        job['description'] = ""
                    
                    jobs.append(job)
                    
                except Exception as e:
                    logger.error(f"Error parsing Glassdoor job card: {str(e)}")
        
        # Check for and handle captchas
        if self.captcha_solver.detect_captcha():
            self.captcha_solver.handle_captcha()
        
        return jobs
    
    def _filter_jobs(self, jobs):
        """Filter jobs based on criteria and previously applied jobs"""
        filtered_jobs = []
        
        # Add skills for matching from resume
        skills = [
            "python", "java", "c++", "javascript", "sql", "mysql", 
            "embedded", "linux", "algorithms", "data structures",
            "machine learning", "software development", "github",
            "circuit", "vlsi", "microcontroller", "digital systems"
        ]
        
        for job in jobs:
            # Skip if already applied
            if any(applied['url'] == job['url'] for applied in self.applied_jobs):
                continue
            
            title = job['title'].lower()
            description = job.get('description', '').lower()
            
            # Check for new grad/entry level indicators in title
            is_entry_level = any(kw.lower() in title for kw in [
                'entry level', 'entry-level', 'new grad', 'junior', 
                'associate', 'university grad', 'recent graduate'
            ])
            
            # If not found in title, check description
            if not is_entry_level and description:
                is_entry_level = any(kw.lower() in description for kw in [
                    'entry level', 'entry-level', 'new grad', 'junior', 
                    'associate', 'university grad', 'recent graduate',
                    '0-2 years', '0-1 years', '1-2 years'
                ])
            
            # Skip if not entry level
            if not is_entry_level:
                continue
                
            # Check for excluded keywords
            if any(exclude.lower() in title for exclude in self.exclude_keywords):
                continue
                
            if description and any(exclude.lower() in description for exclude in self.exclude_keywords):
                continue
            
            # Calculate skill match score
            skill_matches = 0
            for skill in skills:
                if skill in title or (description and skill in description):
                    skill_matches += 1
            
            # Only include jobs with at least 2 skill matches
            if skill_matches >= 2:
                # Add skill match score to job data
                job['skill_score'] = skill_matches
                filtered_jobs.append(job)
            
        # Sort by skill match score (highest first)
        filtered_jobs.sort(key=lambda x: x.get('skill_score', 0), reverse=True)
        
        return filtered_jobs
    
    def apply_for_jobs(self, jobs, max_applications=10):
        """Apply for filtered jobs with rate limiting"""
        applied_count = 0
        failed_count = 0
        
        # Limit number of applications per run
        jobs_to_apply = jobs[:max_applications]
        self.stats["applications_attempted"] = len(jobs_to_apply)
        
        for job in jobs_to_apply:
            try:
                logger.info(f"Attempting to apply for: {job['title']} at {job['company']} ({job['source']})")
                
                # Apply based on source platform
                if job['source'] == 'linkedin':
                    success = self._apply_linkedin(job)
                elif job['source'] == 'indeed':
                    success = self._apply_indeed(job)
                elif job['source'] == 'glassdoor':
                    success = self._apply_glassdoor(job)
                else:
                    logger.warning(f"Unknown source: {job['source']}")
                    success = False
                
                if success:
                    # Record successful application
                    job['date_applied'] = datetime.now().strftime('%Y-%m-%d')
                    job['application_status'] = 'applied'
                    self.applied_jobs.append(job)
                    applied_count += 1
# Record successful application
                    job['date_applied'] = datetime.now().strftime('%Y-%m-%d')
                    job['application_status'] = 'applied'
                    self.applied_jobs.append(job)
                    applied_count += 1
                    self.stats["applications_completed"] += 1
                    logger.info(f"Successfully applied to {job['title']} at {job['company']}")
                    
                    # Save progress after each successful application
                    self._save_applied_jobs()
                    
                    # Random delay between applications (20-45 seconds)
                    time.sleep(random.uniform(20, 45))
                else:
                    failed_count += 1
                    self.stats["applications_failed"] += 1
                    logger.warning(f"Failed to apply to {job['title']} at {job['company']}")
            
            except Exception as e:
                logger.error(f"Error applying to job: {str(e)}")
                failed_count += 1
                self.stats["applications_failed"] += 1
                
                # Take screenshot of error for debugging
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                screenshot_path = f"error_screenshots/{timestamp}.png"
                os.makedirs("error_screenshots", exist_ok=True)
                try:
                    self.driver.save_screenshot(screenshot_path)
                    logger.info(f"Error screenshot saved to {screenshot_path}")
                except:
                    pass
        
        logger.info(f"Application run completed: {applied_count} successful, {failed_count} failed")
        return applied_count, failed_count
    
    def _apply_linkedin(self, job):
        """Apply for a job on LinkedIn"""
        try:
            # Navigate to job page
            self.driver.get(job['url'])
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-unified-top-card"))
            )
            
            # Check if already applied
            try:
                applied_text = self.driver.find_element(By.CSS_SELECTOR, ".jobs-s-apply__applied-status")
                if "applied" in applied_text.text.lower():
                    logger.info(f"Already applied to {job['title']} at {job['company']}")
                    return True
            except NoSuchElementException:
                pass
            
            # Find and click the Apply button
            apply_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".jobs-apply-button"))
            )
            apply_button.click()
            
            # Wait for application form
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-easy-apply-content"))
            )
            
            # Check for captcha
            if self.captcha_solver.detect_captcha():
                self.captcha_solver.handle_captcha()
            
            # Process application steps
            while True:
                # Look for Next/Submit buttons
                try:
                    # Check for next button first
                    next_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((
                            By.CSS_SELECTOR, 
                            "button[aria-label='Continue to next step']"
                        ))
                    )
                    
                    # Fill in fields on current step
                    self._fill_linkedin_form()
                    
                    # Click next
                    next_button.click()
                    time.sleep(2)
                    
                except TimeoutException:
                    # No next button, look for submit button
                    try:
                        submit_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((
                                By.CSS_SELECTOR, 
                                "button[aria-label='Submit application']"
                            ))
                        )
                        
                        # Fill final form fields
                        self._fill_linkedin_form()
                        
                        # Submit application
                        submit_button.click()
                        
                        # Wait for confirmation
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".artdeco-modal__content"))
                        )
                        
                        return True
                        
                    except TimeoutException:
                        # Check if we're stuck on complex questions or external application
                        if self._check_for_complex_application():
                            logger.info(f"Complex application detected for {job['title']} - skipping")
                            return False
                        
                        # Something unexpected happened
                        logger.error(f"Neither next nor submit button found for {job['title']}")
                        return False
            
        except Exception as e:
            logger.error(f"Error during LinkedIn application: {str(e)}")
            return False
    
    def _fill_linkedin_form(self):
        """Fill form fields on LinkedIn application"""
        try:
            # Look for common input fields
            
            # Phone number
            try:
                phone_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='phoneNumber']")
                if not phone_input.get_attribute('value'):
                    self._natural_type(phone_input, "5555551234")  # Replace with actual phone
            except NoSuchElementException:
                pass
            
            # Work experience (years)
            try:
                exp_dropdown = self.driver.find_element(By.CSS_SELECTOR, 
                                                     "select[name='urn:li:form:workExperienceFormElement']")
                exp_dropdown.click()
                # Select 0-1 or entry level option
                options = self.driver.find_elements(By.CSS_SELECTOR, "option")
                for option in options:
                    if any(x in option.text.lower() for x in ["0-1", "entry", "less than 1", "<1"]):
                        option.click()
                        break
            except NoSuchElementException:
                pass
            
            # Education dropdown
            try:
                edu_dropdown = self.driver.find_element(By.CSS_SELECTOR, 
                                                     "select[name*='education']")
                edu_dropdown.click()
                # Select bachelor's degree
                options = self.driver.find_elements(By.CSS_SELECTOR, "option")
                for option in options:
                    if "bachelor" in option.text.lower():
                        option.click()
                        break
            except NoSuchElementException:
                pass
            
            # Resume upload
            try:
                resume_upload = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                resume_upload.send_keys(self.resume_path)
                time.sleep(3)  # Wait for upload
            except NoSuchElementException:
                pass
            
            # Yes/No questions - typically answer "Yes" to qualified questions
            yes_no_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                                                   "input[type='radio'][value='yes']")
            for button in yes_no_buttons:
                button.click()
            
        except Exception as e:
            logger.error(f"Error filling LinkedIn form: {str(e)}")
    
    def _check_for_complex_application(self):
        """Check if application requires complex inputs or external redirect"""
        # Check for text area (long-form questions)
        textareas = self.driver.find_elements(By.TAG_NAME, "textarea")
        if len(textareas) > 0:
            return True
        
        # Look for external application indicators
        external_indicators = [
            "complete application on company website",
            "external site",
            "company's website",
            "continue on company site"
        ]
        
        page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
        for indicator in external_indicators:
            if indicator in page_text:
                return True
        
        return False
    
    def _apply_indeed(self, job):
        """Apply for a job on Indeed"""
        try:
            # Navigate to job page
            self.driver.get(job['url'])
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".jobsearch-JobInfoHeader"))
            )
            
            # Check if already applied
            try:
                applied_text = self.driver.find_element(By.CSS_SELECTOR, ".jobsearch-ResponseIndicators")
                if "applied" in applied_text.text.lower():
                    logger.info(f"Already applied to {job['title']} at {job['company']}")
                    return True
            except NoSuchElementException:
                pass
            
            # Find and click Apply button
            try:
                apply_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".jobsearch-IndeedApplyButton"))
                )
                apply_button.click()
                
                # Wait for application to load in new window or iframe
                time.sleep(3)
                
                # Check if new window opened
                windows = self.driver.window_handles
                if len(windows) > 1:
                    self.driver.switch_to.window(windows[1])
                else:
                    # Check for iframe
                    try:
                        iframe = self.driver.find_element(By.ID, "indeedapply-iframe")
                        self.driver.switch_to.frame(iframe)
                    except:
                        pass
                
                # Check for captcha
                if self.captcha_solver.detect_captcha():
                    self.captcha_solver.handle_captcha()
                
                # Process application steps
                while True:
                    # Look for continue/next button
                    try:
                        continue_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((
                                By.CSS_SELECTOR, 
                                "button[data-testid='continueButton'], button.ia-continueButton"
                            ))
                        )
                        
                        # Fill fields on current step
                        self._fill_indeed_form()
                        
                        # Click continue
                        continue_button.click()
                        time.sleep(2)
                        
                    except TimeoutException:
                        # No continue button, look for submit button
                        try:
                            submit_button = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((
                                    By.CSS_SELECTOR, 
                                    "button[data-testid='submitButton'], button.ia-SubmitButton"
                                ))
                            )
                            
                            # Fill final form fields
                            self._fill_indeed_form()
                            
                            # Submit application
                            submit_button.click()
                            
                            # Wait for confirmation
                            WebDriverWait(self.driver, 10).until(
                                lambda d: "applied" in d.current_url.lower() or 
                                          "thank" in d.current_url.lower() or
                                          "success" in d.current_url.lower()
                            )
                            
                            # Return to main window if needed
                            if len(self.driver.window_handles) > 1:
                                self.driver.close()
                                self.driver.switch_to.window(self.driver.window_handles[0])
                            
                            return True
                            
                        except TimeoutException:
                            # Check if we're stuck on complex questions or external application
                            if self._check_for_complex_application():
                                logger.info(f"Complex application detected for {job['title']} - skipping")
                                
                                # Return to main window if needed
                                if len(self.driver.window_handles) > 1:
                                    self.driver.close()
                                    self.driver.switch_to.window(self.driver.window_handles[0])
                                
                                return False
                            
                            # Something unexpected happened
                            logger.error(f"Neither continue nor submit button found for {job['title']}")
                            
                            # Return to main window if needed
                            if len(self.driver.window_handles) > 1:
                                self.driver.close()
                                self.driver.switch_to.window(self.driver.window_handles[0])
                            
                            return False
                
            except Exception as e:
                logger.error(f"Error applying on Indeed: {str(e)}")
                return False
            
        except Exception as e:
            logger.error(f"Error during Indeed application: {str(e)}")
            return False
    
    def _fill_indeed_form(self):
        """Fill form fields on Indeed application"""
        try:
            # Name fields
            try:
                name_fields = self.driver.find_elements(By.CSS_SELECTOR, "input[name*='name']")
                for field in name_fields:
                    placeholder = field.get_attribute("placeholder").lower()
                    if "first" in placeholder and not field.get_attribute("value"):
                        self._natural_type(field, "John")  # Replace with actual first name
                    elif "last" in placeholder and not field.get_attribute("value"):
                        self._natural_type(field, "Doe")  # Replace with actual last name
            except:
                pass
            
            # Email field
            try:
                email_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='email']")
                if not email_field.get_attribute("value"):
                    self._natural_type(email_field, self.email)
            except:
                pass
            
            # Phone field
            try:
                phone_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='tel']")
                if not phone_field.get_attribute("value"):
                    self._natural_type(phone_field, "5555551234")  # Replace with actual phone
            except:
                pass
            
            # Resume upload
            try:
                resume_upload = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                resume_upload.send_keys(self.resume_path)
                time.sleep(3)  # Wait for upload
            except:
                pass
            
            # Experience dropdowns
            try:
                dropdowns = self.driver.find_elements(By.CSS_SELECTOR, "select")
                for dropdown in dropdowns:
                    if "experience" in dropdown.get_attribute("name").lower():
                        dropdown.click()
                        options = self.driver.find_elements(By.TAG_NAME, "option")
                        for option in options:
                            if any(x in option.text.lower() for x in ["0-1", "entry", "less than 1", "<1"]):
                                option.click()
                                break
            except:
                pass
            
            # Radio buttons for simple yes/no questions - typically answer "Yes" to qualified questions
            try:
                labels = self.driver.find_elements(By.CSS_SELECTOR, "label")
                for label in labels:
                    if "yes" in label.text.lower():
                        label.click()
            except:
                pass
            
        except Exception as e:
            logger.error(f"Error filling Indeed form: {str(e)}")
    
    def _apply_glassdoor(self, job):
        """Apply for a job on Glassdoor"""
        try:
            # Navigate to job page
            self.driver.get(job['url'])
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".jobDetails"))
            )
            
            # Find and click Apply button
            try:
                apply_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.applyButton"))
                )
                apply_button.click()
                
                # Wait for application options
                time.sleep(3)
                
                # Check if there's an "Easy Apply" option vs. external apply
                try:
                    easy_apply = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.easyApply"))
                    )
                    easy_apply.click()
                    
                    # Process Glassdoor Easy Apply
                    return self._process_glassdoor_easy_apply()
                    
                except TimeoutException:
                    # No Easy Apply, likely external application
                    logger.info(f"External application for {job['title']} on Glassdoor - skipping")
                    return False
                
            except TimeoutException:
                logger.error(f"Apply button not found for {job['title']} on Glassdoor")
                return False
            
        except Exception as e:
            logger.error(f"Error during Glassdoor application: {str(e)}")
            return False
    
    def _process_glassdoor_easy_apply(self):
        """Process Glassdoor Easy Apply application flow"""
        try:
            # Glassdoor Easy Apply typically has a multi-step form
            while True:
                # Fill current form
                self._fill_glassdoor_form()
                
                # Look for continue button
                try:
                    continue_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.continueButton"))
                    )
                    continue_button.click()
                    time.sleep(2)
                    
                except TimeoutException:
                    # No continue button, look for submit button
                    try:
                        submit_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.submitButton"))
                        )
                        submit_button.click()
                        
                        # Wait for confirmation
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".applicationSubmitted"))
                        )
                        
                        return True
                        
                    except TimeoutException:
                        # Check if we've reached a complex application
                        if self._check_for_complex_application():
                            logger.info("Complex application on Glassdoor - skipping")
                            return False
                        
                        logger.error("Neither continue nor submit button found on Glassdoor")
                        return False
            
        except Exception as e:
            logger.error(f"Error in Glassdoor Easy Apply process: {str(e)}")
            return False
    
    def _fill_glassdoor_form(self):
        """Fill form fields on Glassdoor application"""
        try:
            # Name fields
            name_fields = self.driver.find_elements(By.CSS_SELECTOR, "input[name*='name']")
            for field in name_fields:
                field_id = field.get_attribute("id").lower()
                if "first" in field_id and not field.get_attribute("value"):
                    self._natural_type(field, "John")  # Replace with actual first name
                elif "last" in field_id and not field.get_attribute("value"):
                    self._natural_type(field, "Doe")  # Replace with actual last name
            
            # Email field
            try:
                email_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='email']")
                if not email_field.get_attribute("value"):
                    self._natural_type(email_field, self.email)
            except:
                pass
            
            # Phone field
            try:
                phone_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='tel']")
                if not phone_field.get_attribute("value"):
                    self._natural_type(phone_field, "5555551234")  # Replace with actual phone
            except:
                pass
            
            # Resume upload
            try:
                resume_upload = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                resume_upload.send_keys(self.resume_path)
                time.sleep(3)  # Wait for upload
            except:
                pass
            
            # Dropdowns for experience, education, etc.
            dropdowns = self.driver.find_elements(By.TAG_NAME, "select")
            for dropdown in dropdowns:
                dropdown_id = dropdown.get_attribute("id").lower()
                if "experience" in dropdown_id:
                    dropdown.click()
                    options = self.driver.find_elements(By.TAG_NAME, "option")
                    for option in options:
                        if any(x in option.text.lower() for x in ["0-1", "entry", "less than 1", "<1"]):
                            option.click()
                            break
                elif "education" in dropdown_id:
                    dropdown.click()
                    options = self.driver.find_elements(By.TAG_NAME, "option")
                    for option in options:
                        if "bachelor" in option.text.lower():
                            option.click()
                            break
            
            # Checkboxes (usually for terms)
            checkboxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
            for checkbox in checkboxes:
                if not checkbox.is_selected():
                    checkbox.click()
            
        except Exception as e:
            logger.error(f"Error filling Glassdoor form: {str(e)}")
    
    def _natural_type(self, element, text):
        """Type text in a human-like manner with variable speed"""
        for char in text:
            element.send_keys(char)
            # Random delay between keystrokes (30-100ms)
            time.sleep(random.uniform(0.03, 0.1))
    
    def generate_report(self):
        """Generate a report of the job search and application results"""
        report = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "stats": self.stats,
            "recently_applied": [
                job for job in self.applied_jobs 
                if datetime.strptime(job['date_applied'], '%Y-%m-%d') >= 
                   datetime.now() - timedelta(days=7)
            ],
            "most_common_skills": self._analyze_skill_requirements()
        }
        
        # Save report to file
        with open(f"report_{datetime.now().strftime('%Y%m%d')}.json", 'w') as f:
            json.dump(report, f, indent=2)
        
        return report
    
    def _analyze_skill_requirements(self):
        """Analyze job descriptions to find most common skills required"""
        skill_keywords = [
            "python", "java", "c++", "javascript", "html", "css", "react", 
            "angular", "vue", "node", "express", "django", "flask", "spring",
            "sql", "mysql", "postgresql", "mongodb", "nosql", "aws", "azure",
            "gcp", "cloud", "docker", "kubernetes", "ci/cd", "jenkins", "git",
            "github", "agile", "scrum", "jira", "linux", "windows", "macos",
            "rest", "api", "microservices", "embedded", "raspberry pi", "arduino"
        ]
        
        skill_counts = {skill: 0 for skill in skill_keywords}
        
        # Count occurrences in job descriptions
        for job in self.applied_jobs:
            description = job.get('description', '').lower()
            if description:
                for skill in skill_keywords:
                    if skill in description:
                        skill_counts[skill] += 1
        
        # Sort by count (descending)
        sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
        
        # Return top 10 skills
        return dict(sorted_skills[:10])
    
    def send_email_report(self, recipient_email=None):
        """Send email report of job application activity"""
        if not recipient_email:
            recipient_email = self.email
            
        # Generate report data
        report_data = self.generate_report()
        
        try:
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = self.email
            msg['To'] = recipient_email
            msg['Subject'] = f"Job Application Report - {datetime.now().strftime('%Y-%m-%d')}"
            
            # Create HTML email body
            html_body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                    .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                    h1, h2 {{ color: #2c3e50; }}
                    .stats {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; }}
                    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background-color: #f2f2f2; }}
                    tr:nth-child(even) {{ background-color: #f9f9f9; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Job Application Bot - Activity Report</h1>
                    <p>Here's a summary of your recent job application activity:</p>
                    
                    <div class="stats">
                        <h2>Statistics</h2>
                        <ul>
                            <li>Jobs Found: {report_data['stats']['jobs_found']}</li>
                            <li>Jobs Filtered: {report_data['stats']['jobs_filtered']}</li>
                            <li>Applications Attempted: {report_data['stats']['applications_attempted']}</li>
                            <li>Applications Completed: {report_data['stats']['applications_completed']}</li>
                            <li>Applications Failed: {report_data['stats']['applications_failed']}</li>
                        </ul>
                    </div>
                    
                    <h2>Recently Applied Jobs</h2>
                    <table>
                        <tr>
                            <th>Job Title</th>
                            <th>Company</th>
                            <th>Source</th>
                            <th>Date Applied</th>
                        </tr>
            """
            
            # Add applied jobs to table
            for job in report_data['recently_applied'][:10]:  # Limit to 10 recent jobs
                html_body += f"""
                        <tr>
                            <td>{job['title']}</td>
                            <td>{job['company']}</td>
                            <td>{job['source']}</td>
                            <td>{job['date_applied']}</td>
                        </tr>
                """
                
            # Close table and add skill analysis
            html_body += """
                    </table>
                    
                    <h2>Most In-Demand Skills</h2>
                    <table>
                        <tr>
                            <th>Skill</th>
                            <th>Mentions</th>
                        </tr>
            """
            
            # Add skills to table
            for skill, count in report_data['most_common_skills'].items():
                html_body += f"""
                        <tr>
                            <td>{skill}</td>
                            <td>{count}</td>
                        </tr>
                """
                
            # Close the HTML
            html_body += """
                    </table>
                    
                    <p>This report was automatically generated by your Job Application Bot.</p>
                </div>
            </body>
            </html>
            """
            
            # Attach HTML content
            msg.attach(MIMEText(html_body, 'html'))
            
            # Attach JSON report
            report_filename = f"report_{datetime.now().strftime('%Y%m%d')}.json"
            with open(report_filename, 'rb') as f:
                attachment = MIMEApplication(f.read(), _subtype='json')
                attachment.add_header('Content-Disposition', 'attachment', filename=report_filename)
                msg.attach(attachment)
            
            # Send email
            smtp_server = "smtp.gmail.com"  # Replace with your SMTP server
            smtp_port = 587
            smtp_username = self.email  # Replace with SMTP username if different
            smtp_password = "your_app_password"  # Replace with app password or actual password
            
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email report sent to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email report: {str(e)}")
            return False
    
    def close(self):
        """Close browser and clean up resources"""
        if self.browser_manager:
            self.browser_manager.close_browser()
        logger.info("Job application bot closed")

def main():
    """Main function to run the job application bot"""
    # Configuration
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
    
    # Initialize job bot
    bot = JobApplicationBot(
        email=config["email"],
        resume_path=config["resume_path"],
        keywords=config["keywords"],
        locations=config["locations"],
        exclude_keywords=config["exclude_keywords"],
        headless=config["headless"]
    )
    
    try:
        # Initialize browser and authenticate
        logger.info("Initializing browser and authenticating...")
        auth_results = bot.initialize()
        
        # Check authentication results
        all_authenticated = all(auth_results.values())
        if not all_authenticated:
            failed_platforms = [p for p, r in auth_results.items() if not r]
            logger.warning(f"Failed to authenticate with: {', '.join(failed_platforms)}")
            
            # Ask user if they want to continue
            if input("Continue with available platforms? (y/n): ").lower() != 'y':
                logger.info("Operation cancelled by user.")
                bot.close()
                return

            # Search for jobs
        logger.info("Searching for jobs...")
        jobs = bot.search_jobs()
        
        # Filter jobs
        logger.info(f"Found {len(jobs)} jobs. Filtering...")
        filtered_jobs = bot.filter_jobs(jobs)
        logger.info(f"{len(filtered_jobs)} jobs remained after filtering.")
        
        # Apply to jobs
        if filtered_jobs:
            logger.info(f"Starting to apply for jobs (max: {config['max_applications']})...")
            applied_count, failed_count = bot.apply_for_jobs(
                filtered_jobs[:config['max_applications']]
            )
            
            # Generate and send report
            logger.info("Generating report...")
            bot.generate_report()
            
            # Send email report
            logger.info("Sending email report...")
            bot.send_email_report()
            
            logger.info(f"Job application run completed: {applied_count} successful, {failed_count} failed")
        else:
            logger.info("No suitable jobs found after filtering.")
        
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")
        traceback.print_exc()
    
    finally:
        # Clean up
        bot.close()
        logger.info("Job application bot session ended")

if __name__ == "__main__":
    main()
