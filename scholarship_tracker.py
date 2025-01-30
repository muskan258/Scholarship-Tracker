import os
from dotenv import load_dotenv
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import schedule
import time
from datetime import datetime, timedelta
import logging
import json
from typing import List, Dict, Optional
import random
import sqlite3
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import hashlib
import win32com.client

# Setup logging with rotation
from logging.handlers import RotatingFileHandler

# Create logs directory if it doesn't exist
Path("logs").mkdir(exist_ok=True)

# Setup rotating file handler
log_handler = RotatingFileHandler(
    'logs/scholarship_tracker.log',
    maxBytes=1024 * 1024,  # 1MB
    backupCount=5
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        log_handler,
        logging.StreamHandler()  # Also print to console
    ]
)

# Load environment variables
load_dotenv()

# Initialize Gemini AI
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables")
genai.configure(api_key=GOOGLE_API_KEY)

# Email Configuration
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

if not all([EMAIL_ADDRESS, EMAIL_PASSWORD, RECIPIENT_EMAIL]):
    raise ValueError("Email configuration incomplete in environment variables")

# Setup requests session with retries
session = requests.Session()
retries = Retry(
    total=5,
    backoff_factor=0.1,
    status_forcelist=[500, 502, 503, 504]
)
session.mount('http://', HTTPAdapter(max_retries=retries))
session.mount('https://', HTTPAdapter(max_retries=retries))

class ScholarshipData:
    """Class to store scholarship information"""
    def __init__(self, title: str, description: str, source: str, url: str, 
                 amount: Optional[str] = None, deadline: Optional[str] = None):
        self.title = title
        self.description = description
        self.source = source
        self.url = url
        self.amount = amount
        self.deadline = deadline
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        """Convert scholarship data to dictionary"""
        return {
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "url": self.url,
            "amount": self.amount,
            "deadline": self.deadline,
            "timestamp": self.timestamp
        }

# Trusted scholarship sources with their specific configurations
SCHOLARSHIP_SOURCES = {
    "National Scholarship Portal": {
        "url": "https://scholarships.gov.in/",
        "selectors": {
            "scholarships": ".scholarship-item",
            "title": ".scholarship-title",
            "description": ".description",
            "deadline": ".deadline",
            "amount": ".amount"
        }
    },
    "Buddy4Study": {
        "url": "https://www.buddy4study.com/scholarships/",
        "api_url": "https://www.buddy4study.com/api/scholarships/search",
        "params": {
            "level": ["Graduate", "Post Graduate"],
            "type": ["National", "International"]
        }
    },
    "AICTE": {
        "url": "https://www.aicte-india.org/schemes/students-development-schemes",
        "selectors": {
            "scholarships": ".schemes-item",
            "title": ".scheme-title",
            "description": ".scheme-description",
            "deadline": ".scheme-deadline",
            "amount": ".scheme-amount"
        }
    },
    "UGC Scholarships": {
        "url": "https://www.ugc.ac.in/page/Scholarships-and-Fellowships.aspx",
        "selectors": {
            "scholarships": ".scholarship-list-item",
            "title": ".title",
            "description": ".description",
            "deadline": ".deadline",
            "amount": ".amount"
        }
    },
    "DBT India": {
        "url": "http://dbtindia.gov.in/schemes-programmes/building-young-careers/scholarships",
        "selectors": {
            "scholarships": ".scholarship-item",
            "title": ".title",
            "description": ".content",
            "deadline": ".deadline",
            "amount": ".stipend"
        }
    }
}

# Add known scholarships that are currently available
AVAILABLE_SCHOLARSHIPS = [
    ScholarshipData(
        title="Prime Minister's Research Fellowship (PMRF)",
        description="""Direct admission to PhD programs at IITs/IISc for students who have completed/are pursuing final year B.Tech/Integrated M.Tech/M.Sc. 
        Benefits: Fellowship of Rs.70,000-80,000 per month plus research grant of Rs.2 lakhs per year.""",
        source="Government of India",
        url="https://pmrf.in/",
        amount="Rs. 70,000-80,000 per month + Research grant",
        deadline="February 28, 2025"
    ),
    ScholarshipData(
        title="AICTE PG (GATE/GPAT) Scholarship",
        description="""For GATE/GPAT qualified students pursuing M.E./M.Tech/M.Arch and M.Pharma courses.
        Monthly stipend for 24 months or duration of course, whichever is less.""",
        source="AICTE",
        url="https://www.aicte-india.org/schemes/students-development-schemes/PG-Scholarship-Scheme",
        amount="Rs. 12,400 per month",
        deadline="Ongoing"
    ),
    ScholarshipData(
        title="National Overseas Scholarship",
        description="""For SC, ST, landless agricultural laborers and traditional artisans' children for pursuing Master's level courses and PhD abroad.
        Covers tuition fees, living expenses, travel, and more.""",
        source="Ministry of Social Justice and Empowerment",
        url="https://nosmsje.gov.in/",
        amount="Full funding including tuition fees and living expenses",
        deadline="March 31, 2025"
    ),
    ScholarshipData(
        title="Post Graduate Indira Gandhi Scholarship for Single Girl Child",
        description="""For single girl child to pursue non-professional PG courses. 
        Girl students up to the age of 30 years (as on 1st July of the year) can apply.""",
        source="UGC",
        url="https://www.ugc.ac.in/",
        amount="Rs. 36,200 per annum",
        deadline="March 15, 2025"
    ),
    ScholarshipData(
        title="Post Graduate Merit Scholarship for University Rank Holders",
        description="""For students who have secured first and second rank in undergraduate degree for pursuing post graduation.
        Valid for all streams except technical/professional courses.""",
        source="UGC",
        url="https://scholarships.gov.in",
        amount="Rs. 3,100 per month for 2 years",
        deadline="February 28, 2025"
    ),
    ScholarshipData(
        title="Kishore Vaigyanik Protsahan Yojana (KVPY)",
        description="""Fellowship program to encourage students to pursue research careers in Science.
        For students from Class 11 to 1st year of any UG Program.""",
        source="Department of Science and Technology",
        url="http://www.kvpy.iisc.ernet.in/",
        amount="Rs. 5,000-7,000 per month + Summer Fellowship",
        deadline="Ongoing"
    ),
    ScholarshipData(
        title="CSIR Junior Research Fellowship",
        description="""For pursuing PhD in Science, Engineering, Medicine, Agriculture, Pharmacy, and other related fields.
        Candidates must qualify CSIR-UGC NET for JRF.""",
        source="CSIR",
        url="https://csirhrdg.res.in/",
        amount="Rs. 31,000 per month + HRA",
        deadline="June 2025 (Next cycle)"
    )
]

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('scholarships.db')
        self.create_tables()

    def create_tables(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS scholarships (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    source TEXT,
                    url TEXT,
                    amount TEXT,
                    deadline TEXT,
                    timestamp DATETIME,
                    sent_in_email BOOLEAN DEFAULT FALSE
                )
            ''')

    def add_scholarship(self, scholarship):
        scholarship_id = hashlib.md5(
            f"{scholarship.title}{scholarship.source}".encode()
        ).hexdigest()
        
        with self.conn:
            self.conn.execute('''
                INSERT OR REPLACE INTO scholarships 
                (id, title, description, source, url, amount, deadline, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                scholarship_id,
                scholarship.title,
                scholarship.description,
                scholarship.source,
                scholarship.url,
                scholarship.amount,
                scholarship.deadline,
                scholarship.timestamp
            ))

    def mark_as_sent(self, scholarship_ids):
        with self.conn:
            self.conn.executemany(
                'UPDATE scholarships SET sent_in_email = TRUE WHERE id = ?',
                [(id,) for id in scholarship_ids]
            )

    def get_unsent_scholarships(self):
        cursor = self.conn.execute('''
            SELECT * FROM scholarships 
            WHERE sent_in_email = FALSE 
            AND timestamp > datetime('now', '-7 days')
        ''')
        return cursor.fetchall()

def get_available_scholarships() -> List[ScholarshipData]:
    """Return list of currently available scholarships"""
    return AVAILABLE_SCHOLARSHIPS

def fetch_scholarship_data(source_name: str, config: Dict) -> List[ScholarshipData]:
    """Fetch scholarship information with improved handling for different sources"""
    scholarships = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }

        if source_name == "Buddy4Study":
            # Special handling for Buddy4Study API
            scholarships.extend(fetch_buddy4study_scholarships(config))
        else:
            response = session.get(config['url'], headers=headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try different selector patterns
            items = soup.select(config['selectors']['scholarships'])
            
            for item in items:
                title = extract_text(item, config['selectors']['title'])
                description = extract_text(item, config['selectors']['description'])
                deadline = extract_text(item, config['selectors']['deadline'])
                amount = extract_text(item, config['selectors']['amount'])
                
                if title and description:
                    scholarship = ScholarshipData(
                        title=clean_text(title),
                        description=clean_text(description),
                        source=source_name,
                        url=config['url'],
                        amount=clean_text(amount) if amount else None,
                        deadline=parse_deadline(deadline) if deadline else None
                    )
                    scholarships.append(scholarship)
        
        logging.info(f"Successfully fetched {len(scholarships)} scholarships from {source_name}")
        return scholarships
    
    except Exception as e:
        logging.error(f"Error fetching data from {source_name}: {str(e)}")
        return []

def fetch_buddy4study_scholarships(config: Dict) -> List[ScholarshipData]:
    """Special handling for Buddy4Study API"""
    scholarships = []
    try:
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = session.post(
            config['api_url'],
            json=config['params'],
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        for item in data.get('scholarships', []):
            scholarship = ScholarshipData(
                title=item.get('title', ''),
                description=item.get('description', ''),
                source="Buddy4Study",
                url=item.get('apply_url', config['url']),
                amount=item.get('amount', ''),
                deadline=item.get('deadline', '')
            )
            scholarships.append(scholarship)
            
        return scholarships
    except Exception as e:
        logging.error(f"Error fetching from Buddy4Study API: {str(e)}")
        return []

def clean_text(text: str) -> str:
    """Clean and normalize text"""
    if not text:
        return ""
    return ' '.join(text.split())

def parse_deadline(deadline_text: str) -> str:
    """Parse and standardize deadline format"""
    try:
        # Add deadline parsing logic here
        return deadline_text.strip()
    except Exception:
        return deadline_text

def extract_text(item: BeautifulSoup, selector: str) -> Optional[str]:
    """Safely extract text from BeautifulSoup element"""
    try:
        element = item.select_one(selector)
        return element.text.strip() if element else None
    except Exception:
        return None

def process_with_gemini(scholarships: List[ScholarshipData]) -> str:
    """Process scholarship data using Gemini AI with improved prompting for Indian context"""
    try:
        model = genai.GenerativeModel('gemini-pro')
        scholarships_data = [s.to_dict() for s in scholarships]
        
        prompt = f"""
        Create a comprehensive scholarship update for Indian students. Format the output in clean HTML with proper styling.
        Use this exact structure for each scholarship:

        <div class="scholarship">
            <h2>[SCHOLARSHIP_TITLE]</h2>
            <p class="deadline">📅 Deadline: [DEADLINE]</p>
            <p class="amount">💰 Amount: [AMOUNT]</p>
            <div class="details">
                <h3>Eligibility:</h3>
                <ul>
                    [ELIGIBILITY_POINTS]
                </ul>
                <h3>Required Documents:</h3>
                <ul>
                    [REQUIRED_DOCUMENTS]
                </ul>
                <h3>How to Apply:</h3>
                <p>[APPLICATION_PROCESS]</p>
                <p><a href="[URL]" target="_blank">Apply Now →</a></p>
            </div>
        </div>

        Organize scholarships into these categories, each with its own section:

        1. Urgent Deadlines (Next 30 Days)
        2. Government Scholarships
           - Central Government
           - State Government
           - Research Fellowships
        3. Program-Specific
           - Bachelor's Degree
           - Master's Degree
           - PhD Programs
        4. Special Categories
           - Merit-based
           - Need-based
           - Women-specific
           - SC/ST/OBC
        5. International Opportunities

        For each scholarship:
        • Make deadlines stand out (use class="deadline")
        • Format amounts clearly (use class="amount")
        • List eligibility criteria as bullet points
        • Include direct application links
        • Add important notes or tips
        
        Scholarships data: {json.dumps(scholarships_data, indent=2)}
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logging.error(f"Error processing with Gemini: {str(e)}")
        return "Error processing scholarship data. Please check the log for details."

def send_email(content: str) -> bool:
    """Send email using Windows Mail via COM interface"""
    try:
        recipient_email = os.getenv('RECIPIENT_EMAIL', 'muskan7892gupta@gmail.com')
        
        outlook = win32com.client.Dispatch('Outlook.Application')
        mail = outlook.CreateItem(0)
        
        mail.Subject = f'🎓 Scholarship Updates - {datetime.now().strftime("%d %B %Y")}'
        mail.To = recipient_email
        
        html_content = f"""
        <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    /* ... Previous styles ... */
                    .share-button {{
                        display: inline-block;
                        background-color: #25D366;
                        color: white;
                        padding: 8px 15px;
                        border-radius: 4px;
                        text-decoration: none;
                        margin: 5px;
                        font-size: 0.9em;
                    }}
                    .share-button:hover {{
                        opacity: 0.9;
                    }}
                    .filter-section {{
                        background-color: #f8f9fa;
                        padding: 15px;
                        margin: 20px;
                        border-radius: 4px;
                    }}
                    .filter-button {{
                        background-color: #6c757d;
                        color: white;
                        border: none;
                        padding: 5px 10px;
                        margin: 2px;
                        border-radius: 3px;
                        cursor: pointer;
                    }}
                    .filter-button:hover {{
                        background-color: #5a6268;
                    }}
                    .scholarship-tag {{
                        display: inline-block;
                        background-color: #e9ecef;
                        padding: 2px 8px;
                        border-radius: 12px;
                        font-size: 0.8em;
                        margin: 2px;
                    }}
                    .deadline-urgent {{
                        animation: blink 1s infinite;
                    }}
                    @keyframes blink {{
                        50% {{ opacity: 0.5; }}
                    }}
                    @media (max-width: 600px) {{
                        .container {{ margin: 10px; }}
                        .scholarship {{ margin: 10px; padding: 10px; }}
                    }}
                    .print-button {{
                        background-color: #6c757d;
                        color: white;
                        padding: 8px 15px;
                        border-radius: 4px;
                        text-decoration: none;
                        margin: 5px;
                        cursor: pointer;
                    }}
                    .bookmark-button {{
                        float: right;
                        background: none;
                        border: none;
                        color: #ffc107;
                        cursor: pointer;
                        font-size: 1.2em;
                    }}
                    .social-share {{
                        text-align: center;
                        margin: 20px;
                        padding: 10px;
                        background-color: #f8f9fa;
                        border-radius: 4px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎓 Scholarship Updates</h1>
                        <p>{datetime.now().strftime('%d %B %Y')}</p>
                        <button onclick="window.print()" class="print-button">🖨️ Print this page</button>
                    </div>
                    
                    <div class="filter-section no-print">
                        <h3>Quick Filters:</h3>
                        <button class="filter-button" onclick="filterScholarships('urgent')">Urgent Deadlines</button>
                        <button class="filter-button" onclick="filterScholarships('government')">Government</button>
                        <button class="filter-button" onclick="filterScholarships('masters')">Masters</button>
                        <button class="filter-button" onclick="filterScholarships('bachelors')">Bachelors</button>
                        <button class="filter-button" onclick="filterScholarships('all')">Show All</button>
                    </div>
                    
                    <div class="note">
                        <strong>Important:</strong> This update includes both currently available and newly added scholarship opportunities.
                        <p>💡 Pro tip: Use the filters above to find relevant scholarships quickly!</p>
                    </div>
                    
                    {content}
                    
                    <div class="note">
                        <h3>📝 Important Tips:</h3>
                        <ul>
                            <li>Always verify deadlines on official websites</li>
                            <li>Keep these documents ready:
                                <ul>
                                    <li>Academic transcripts</li>
                                    <li>Income certificate</li>
                                    <li>Category certificate (if applicable)</li>
                                    <li>Passport size photographs</li>
                                    <li>Bank account details</li>
                                    <li>Aadhar card</li>
                                </ul>
                            </li>
                            <li>Set reminders for approaching deadlines</li>
                            <li>Start applications early to avoid last-minute issues</li>
                        </ul>
                    </div>
                    
                    <div class="social-share no-print">
                        <h3>Share these opportunities:</h3>
                        <a href="#" class="share-button" style="background-color: #25D366" 
                           onclick="window.open('https://wa.me/?text=' + encodeURIComponent('Check out these scholarship opportunities! 🎓'))">
                           Share on WhatsApp
                        </a>
                        <a href="#" class="share-button" style="background-color: #0088cc"
                           onclick="window.open('https://telegram.me/share/url?url=' + encodeURIComponent(window.location.href))">
                           Share on Telegram
                        </a>
                    </div>
                    
                    <div class="footer">
                        <p>To unsubscribe from these updates, please reply with 'UNSUBSCRIBE'</p>
                        <p><small>Scholarship information is collected from official sources. Always verify details on official websites.</small></p>
                        <p><small>Last updated: {datetime.now().strftime('%d %B %Y %I:%M %p')}</small></p>
                    </div>
                </div>
                
                <script>
                function filterScholarships(type) {{
                    const scholarships = document.querySelectorAll('.scholarship');
                    scholarships.forEach(scholarship => {{
                        if (type === 'all') {{
                            scholarship.style.display = 'block';
                            return;
                        }}
                        const text = scholarship.textContent.toLowerCase();
                        const show = type === 'urgent' ? scholarship.querySelector('.deadline-urgent') :
                                   text.includes(type);
                        scholarship.style.display = show ? 'block' : 'none';
                    }});
                }}
                
                function updateDeadlines() {{
                    const deadlines = document.querySelectorAll('.deadline');
                    deadlines.forEach(deadline => {{
                        const text = deadline.textContent;
                        const date = new Date(text.split(':')[1]);
                        const now = new Date();
                        const diff = Math.floor((date - now) / (1000 * 60 * 60 * 24));
                        if (diff <= 7 && diff >= 0) {{
                            deadline.classList.add('deadline-urgent');
                        }}
                    }});
                }}
                
                updateDeadlines();
                </script>
            </body>
        </html>
        """
        
        mail.HTMLBody = html_content
        mail.Send()
        
        logging.info(f"Email sent successfully to {recipient_email}")
        return True

    except Exception as e:
        logging.error(f"Error sending email: {str(e)}")
        return False

def process_scholarships():
    """Process and display available scholarships"""
    try:
        # Get available scholarships
        scholarships = get_available_scholarships()
        
        # Process with Gemini
        formatted_content = process_with_gemini(scholarships)
        
        # Send email
        if formatted_content:
            send_email(formatted_content)
            logging.info("Successfully sent scholarship update email")
        else:
            logging.error("No content generated for email")
            
    except Exception as e:
        logging.error(f"Error in processing scholarships: {str(e)}")

def test_scholarship_data():
    """Test the scholarship data for completeness and validity"""
    scholarships = get_available_scholarships()
    issues = []
    
    for scholarship in scholarships:
        # Test for required fields
        if not scholarship.title:
            issues.append(f"Missing title in scholarship: {scholarship.source}")
        if not scholarship.description:
            issues.append(f"Missing description in scholarship: {scholarship.title}")
        if not scholarship.url:
            issues.append(f"Missing URL in scholarship: {scholarship.title}")
            
        # Test URL validity
        try:
            response = requests.head(scholarship.url, timeout=5)
            if response.status_code != 200:
                issues.append(f"Invalid URL for scholarship: {scholarship.title}")
        except Exception as e:
            issues.append(f"Error checking URL for {scholarship.title}: {str(e)}")
            
        # Check deadline format and validity
        if scholarship.deadline:
            try:
                if scholarship.deadline.lower() != "ongoing":
                    datetime.strptime(scholarship.deadline, "%B %d, %Y")
            except ValueError:
                issues.append(f"Invalid deadline format in scholarship: {scholarship.title}")
                
        # Check amount format
        if scholarship.amount and not any(currency in scholarship.amount.lower() for currency in ['rs', 'inr', '₹']):
            issues.append(f"Amount may be missing currency in scholarship: {scholarship.title}")
    
    return issues

def validate_email_config():
    """Validate email configuration"""
    issues = []
    required_vars = ['EMAIL_ADDRESS', 'RECIPIENT_EMAIL']
    
    for var in required_vars:
        if not os.getenv(var):
            issues.append(f"Missing {var} in environment configuration")
    
    return issues

def enhance_scholarship_content(content: str) -> str:
    """Enhance the scholarship content with additional features"""
    try:
        # Add sharing buttons
        social_buttons = """
        <div class="social-share">
            <h3>Share this opportunity:</h3>
            <a href="#" class="share-button" onclick="window.open('https://wa.me/?text=' + encodeURIComponent(document.title + ' - Check this scholarship opportunity!'), '_blank')">
                Share on WhatsApp
            </a>
            <a href="#" class="share-button" onclick="window.open('https://telegram.me/share/url?url=' + encodeURIComponent(window.location.href), '_blank')">
                Share on Telegram
            </a>
        </div>
        """
        
        # Add deadline countdown
        deadline_script = """
        <script>
        function updateCountdown() {
            const deadlines = document.querySelectorAll('.deadline');
            deadlines.forEach(deadline => {
                const dateStr = deadline.getAttribute('data-date');
                if (dateStr && dateStr.toLowerCase() !== 'ongoing') {
                    const deadlineDate = new Date(dateStr);
                    const now = new Date();
                    const diff = deadlineDate - now;
                    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
                    if (days > 0) {
                        deadline.innerHTML += ` (${days} days remaining)`;
                    }
                }
            });
        }
        updateCountdown();
        </script>
        """
        
        # Add print-friendly version
        print_style = """
        <style>
        @media print {
            body { background: white; }
            .no-print { display: none; }
            .scholarship { break-inside: avoid; }
            a { text-decoration: underline; }
            .header { background: none; color: black; }
        }
        </style>
        """
        
        # Add to content
        enhanced_content = f"{print_style}\n{content}\n{social_buttons}\n{deadline_script}"
        return enhanced_content
        
    except Exception as e:
        logging.error(f"Error enhancing content: {str(e)}")
        return content

def main():
    """Main function to fetch and process scholarship updates with testing"""
    try:
        # Validate configuration
        email_issues = validate_email_config()
        if email_issues:
            for issue in email_issues:
                logging.error(issue)
            return
        
        # Test scholarship data
        data_issues = test_scholarship_data()
        if data_issues:
            for issue in data_issues:
                logging.warning(issue)
        
        # Process scholarships
        scholarships = get_available_scholarships()
        if not scholarships:
            logging.error("No scholarships available to process")
            return
            
        # Process with Gemini
        content = process_with_gemini(scholarships)
        if not content:
            logging.error("Failed to generate content")
            return
            
        # Enhance content
        enhanced_content = enhance_scholarship_content(content)
        
        # Send email
        if send_email(enhanced_content):
            logging.info("Successfully processed and sent scholarship updates")
        else:
            logging.error("Failed to send email")
            
    except Exception as e:
        logging.error(f"Error in main: {str(e)}")

if __name__ == "__main__":
    main()
