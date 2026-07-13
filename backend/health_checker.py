import requests
import re
import json
import ssl
import socket
import os
from urllib.parse import urlparse, urljoin
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

# Pydantic models for request/response
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


@dataclass
class PillarScore:
    name: str
    label: str
    score: int = 0
    max_score: int = 0
    weight: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    wins: List[str] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        if self.max_score == 0:
            return 0.0
        return round((self.score / self.max_score) * 100, 1)


class BusinessRequest(BaseModel):
    business_name: str
    website_url: Optional[str] = None


class BatchRequest(BaseModel):
    businesses: List[BusinessRequest]


class DigitalHealthChecker:
    """
    Deep Research Digital Health Analyzer - 7 Pillar Analysis
    """
    
    # Pillar configuration
    PILLAR_CONFIG = {
        "website_presence": {"max": 20, "weight": 0.20, "label": "Website Presence", "icon": "🌐"},
        "google_business": {"max": 20, "weight": 0.20, "label": "Google Business Profile", "icon": "📍"},
        "social_media": {"max": 15, "weight": 0.15, "label": "Social Media Presence", "icon": "📱"},
        "mobile_friendly": {"max": 15, "weight": 0.15, "label": "Mobile Friendliness", "icon": "📲"},
        "online_reviews": {"max": 10, "weight": 0.10, "label": "Online Reviews", "icon": "⭐"},
        "seo_basics": {"max": 10, "weight": 0.10, "label": "SEO Basics", "icon": "🔍"},
        "contact_accessibility": {"max": 10, "weight": 0.10, "label": "Contact Accessibility", "icon": "📞"},
    }

    HEALTH_THRESHOLDS = {
        80: ("Digitally Healthy", "green", "🟢", "excellent"),
        60: ("Needs Improvement", "yellow", "🟡", "fair"),
        40: ("Seriously Behind", "orange", "🟠", "poor"),
        0: ("Digitally Invisible", "red", "🔴", "critical"),
    }

    def __init__(self, business_name: str, website_url: Optional[str] = None):
        self.business_name = business_name.strip()
        self.website_url = website_url.strip() if website_url else None
        self.normalized_name = self._normalize_name(business_name)
        
        # Runtime state
        self.resp = None
        self.html = ""
        self.final_url = ""
        self.headers = {}
        self.resp_time = 0
        self._fetch_start = 0
        
        # Results
        self.pillars: List[PillarScore] = []
        self.issues: List[str] = []
        self.wins: List[str] = []
        self.recommendations: List[Dict[str, str]] = []
        self.metadata: Dict[str, Any] = {}
        
        # HTTP session with retries
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        
        # Initialize pillars
        self.pillars = []
        for k, v in self.PILLAR_CONFIG.items():
            self.pillars.append(PillarScore(
                name=k, 
                max_score=v["max"], 
                weight=v["weight"], 
                label=v["label"]
            ))
        
        self.PILLAR_CONFIG = {
            "website_presence": {"max": 20, "weight": 0.20, "label": "Website Presence", "icon": "🌐"},
            "google_business": {"max": 20, "weight": 0.20, "label": "Google Business Profile", "icon": "📍"},
            "social_media": {"max": 15, "weight": 0.15, "label": "Social Media Presence", "icon": "📱"},
            "mobile_friendly": {"max": 15, "weight": 0.15, "label": "Mobile Friendliness", "icon": "📲"},
            "online_reviews": {"max": 10, "weight": 0.10, "label": "Online Reviews", "icon": "⭐"},
            "seo_basics": {"max": 10, "weight": 0.10, "label": "SEO Basics", "icon": "🔍"},
            "contact_accessibility": {"max": 10, "weight": 0.10, "label": "Contact Accessibility", "icon": "📞"},
        }
        
        self.HEALTH_THRESHOLDS = {
            80: ("Digitally Healthy", "green", "🟢", "excellent"),
            60: ("Needs Improvement", "yellow", "🟡", "fair"),
            40: ("Seriously Behind", "orange", "🟠", "poor"),
            0: ("Digitally Invisible", "red", "🔴", "critical"),
        }
        
        self.issues: List[str] = []
        self.wins: List[str] = []
        self.recommendations: List[Dict[str, str]] = []
        self.metadata: Dict[str, Any] = {}
        self._fetch_start = 0
        
        # HTTP session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        
        # Initialize pillars
        self.pillars = []
        for k, v in self.PILLAR_CONFIG.items():
            self.pillars.append(PillarScore(
                name=k, 
                max_score=v["max"], 
                weight=v["weight"], 
                label=v["label"]
            ))
        
        self.PILLAR_CONFIG = {
            "website_presence": {"max": 20, "weight": 0.20, "label": "Website Presence", "icon": "🌐"},
            "google_business": {"max": 20, "weight": 0.20, "label": "Google Business Profile", "icon": "📍"},
            "social_media": {"max": 15, "weight": 0.15, "label": "Social Media Presence", "icon": "📱"},
            "mobile_friendly": {"max": 15, "weight": 0.15, "label": "Mobile Friendliness", "icon": "📲"},
            "online_reviews": {"max": 10, "weight": 0.10, "label": "Online Reviews", "icon": "⭐"},
            "seo_basics": {"max": 10, "weight": 0.10, "label": "SEO Basics", "icon": "🔍"},
            "contact_accessibility": {"max": 10, "weight": 0.10, "label": "Contact Accessibility", "icon": "📞"},
        }
        
        self.HEALTH_THRESHOLDS = {
            80: ("Digitally Healthy", "green", "🟢", "excellent"),
            60: ("Needs Improvement", "yellow", "🟡", "fair"),
            40: ("Seriously Behind", "orange", "🟠", "poor"),
            0: ("Digitally Invisible", "red", "🔴", "critical"),
        }
        
        self.issues: List[str] = []
        self.wins: List[str] = []
        self.recommendations: List[Dict[str, str]] = []
        self.metadata: Dict[str, Any] = {}
        self._fetch_start = 0

    def _normalize_name(self, name: str) -> str:
        return re.sub(r'[^\w\s]', '', name.lower()).strip()

    def run_all_checks(self) -> Dict[str, Any]:
        """Execute all 7 pillars and return comprehensive report"""
        start_time = time.time()
        
        try:
            # Fetch website if URL provided
            if self.website_url:
                self._fetch_website()
            
            # Run all 7 pillars
            self._check_website_presence()
            self._check_google_business()
            self._check_social_media()
            self._check_mobile_friendly()
            self._check_online_reviews()
            self._check_seo_basics()
            self._check_contact_accessibility()
            
            # Calculate totals
            self._calculate_totals()
            self._generate_health_status()
            self._generate_recommendations()
            
        except Exception as e:
            return self._error_response(str(e))
        
        execution_time = round(time.time() - self._fetch_start if hasattr(self, '_fetch_start') else time.time(), 2)
        
        return self._build_report(0)

    def _fetch_website(self):
        """Fetch website with comprehensive error handling"""
        url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
        
        self._fetch_start = time.time()
        
        try:
            self.resp = requests.get(
                self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}',
                timeout=10,
                allow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                },
                allow_redirects=True
            )
            self.final_url = self.resp.url
            self.html = self.resp.text
            self.headers = dict(self.resp.headers)
        except requests.exceptions.Timeout:
            self.resp = None
            self.html = ""
            self.issues.append("❌ Website request timed out (>10s)")
        except requests.exceptions.ConnectionError:
            self.resp = None
            self.html = ""
            self.issues.append("❌ Could not connect to website")
        except Exception as e:
            self.resp = None
            self.html = ""
            self.issues.append(f"⚠️ Fetch error: {str(e)[:100]}")

    # ============================================================
    # PILLAR 1: WEBSITE PRESENCE (20 pts)
    # ============================================================
    
    def _check_website_presence(self):
        """Pillar 1: Website Presence - 20 points"""
        p = self._get_pillar("website_presence")
        p.details = {"checks": {}}
        
        if not self.website_url:
            self._add_issue(p, "❌ No website URL provided — critical gap")
            p.details["checks"]["reachable"] = False
            self._finalize_pillar("website_presence", 20)
            return
        
        p.details["url_checked"] = self.website_url
        
        if not self.resp or self.resp.status_code != 200:
            status = self.resp.status_code if self.resp else "unreachable"
            self._add_issue("website_presence", f"❌ Website unreachable (status: {status})")
            self._finalize_pillar("website_presence", 20)
            return
        
        # 1. Reachability (8 pts)
        score = 8
        self._add_win("website_presence", "✅ Website is live and accessible")
        
        # HTTPS (4 pts)
        if self.resp.url.startswith('https://'):
            score += 4
        else:
            self._add_issue("website_presence", "⚠️ Website not using HTTPS (security risk)")
        
        # HTML content (2 pts)
        content_type = self.resp.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            score += 2
        
        # Load time (3 pts)
        load_time = self.resp.elapsed.total_seconds() if hasattr(self.resp, 'elapsed') else 0
        if load_time < 1.5:
            self._add_win("✅ Website loads quickly")
        elif load_time < 3:
            pass
        else:
            self._add_issue("⚠️ Website load time is slow")
        
        # Security headers (2 pts)
        security_headers = self._check_security_headers()
        if security_headers >= 4:
            self._add_win("✅ Good security headers")
        elif self._security_score >= 2:
            pass
        else:
            self._add_issue("⚠️ Missing security headers")
        
        # Technology stack detection
        tech_stack = self._detect_tech_stack()
        
        self._finalize_pillar("website_presence", 20)

    # ============================================================
    # PILLAR 2: GOOGLE BUSINESS PROFILE (20 pts)
    # ============================================================
    
    def _check_google_business(self):
        p = self._get_pillar("google_business")
        name_lower = self.business_name.lower()
        
        gbp_indicators = [
            'pvt', 'ltd', 'private', 'limited', 'company', 'store', 'shop',
            'restaurant', 'hotel', 'salon', 'clinic', 'center', 'centre',
            'enterprise', 'industries', 'inc', 'llc', 'corp', 'gmbh',
            'ltd', 'limited', 'services', 'solutions', 'group', 'partners'
        ]
        
        has_gbp_indicator = any(ind in self.normalized_name for ind in gbp_indicators)
        if has_gbp_indicator:
            self._add_win("✅ Business name suggests formal registration")
        else:
            self._add_issue("⚠️ Business name doesn't indicate formal registration — may lack GBP")
        
        if self.website_url:
            self._add_win("Website available for GBP verification")
        
        # Check for Google Maps embed
        if 'maps.google.com' in self.html.lower() or 'maps/embed' in self.html.lower():
            self._add_win("✅ Google Maps embed detected")
        
        # Check for LocalBusiness schema
        if self._has_localbusiness_schema():
            self._add_win("✅ LocalBusiness schema markup detected")
        
        self._finalize_pillar("google_business", 20)
    
    # ============================================================
    # PILLAR 3: SOCIAL MEDIA (15 pts)
    # ============================================================
    
    def _check_social_media(self):
        p = self._get_pillar("social_media")
        social_platforms = {
            'facebook': ['facebook.com', 'fb.com', 'facebook'],
            'instagram': ['instagram.com', 'insta'],
            'twitter': ['twitter.com', 'x.com', 'twitter'],
            'linkedin': ['linkedin.com'],
            'youtube': ['youtube.com', 'youtu.be'],
            'tiktok': ['tiktok.com'],
        }
        
        found = []
        if self.resp and self.resp.status_code == 200:
            html_lower = self.html.lower()
            for platform, domains in social_platforms.items():
                for domain in domains:
                    if domain in self.html.lower():
                        if platform not in found:
                            found.append(platform)
                        break
        
        name_lower = self.business_name.lower()
        for platform, keywords in {
            'facebook': ['facebook'], 
            'instagram': ['instagram', 'insta'], 
            'twitter': ['twitter', 'x.com'], 
            'linkedin': ['linkedin'],
            'youtube': ['youtube'], 
            'tiktok': ['tiktok']
        }.items():
            for kw in keywords:
                if kw in self.normalized_name:
                    if platform not in found:
                        found.append(platform)
                    break
        
        score = min(len(found) * 3, 12)
        if found:
            if 'facebook' in found: 
                pass
            if 'instagram' in found: 
                pass
            if 'linkedin' in found: 
                pass
        else:
            self._add_issue("❌ No social media presence detected")
        
        if len(found) >= 4:
            self._add_win("✅ Strong multi-platform social presence")
        
        self._finalize_pillar("social_media", 15)

    def _check_mobile_friendly(self):
        score = 0
        details = {}
        
        if not self.website_url or not self.resp or self.resp.status_code != 200:
            self.issues.append("❌ No website to check for mobile friendliness")
            self.scores['mobile_friendly'] = 0
            self.details['mobile_friendly'] = details
            return score
        
        html = self.html.lower()
        
        viewport = '<meta name="viewport"' in self.html.lower()
        if viewport:
            score += 5
            details['viewport_meta'] = True
        else:
            self.issues.append("⚠️ Website not optimized for mobile (no viewport meta)")
        
        media_queries = '@media' in html
        if media_queries:
            score += 4
            self._add_win("✅ CSS media queries detected")
        else:
            self.issues.append("⚠️ No media queries — may not be responsive")
        
        has_responsive_images = 'srcset' in self.html.lower() or 'picture' in html
        if has_responsive_images:
            score += 2
            details['responsive_images'] = True
        
        has_touch_friendly = any(x in html for x in ['touch-action', 'pointer-events', 'user-select'])
        if has_touch_friendly:
            score += 1
        
        no_horizontal_scroll = 'overflow-x: hidden' in html or 'max-width: 100%' in html
        if no_horizontal_scroll:
            score += 1
        
        mobile_ua_resp = None
        try:
            mobile_ua_resp = requests.get(self.final_url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15'
            })
            mobile_html = mobile_ua_resp.text.lower()
            if '<meta name="viewport"' in mobile_html:
                score += 1
        except:
            pass
        
        if not viewport:
            score = max(0, score - 2)
        
        self.scores['mobile_friendly'] = min(score, 15)
        self.details['mobile_friendly'] = details
        return min(score, 15)
    
    def _check_online_reviews(self):
        score = 0
        details = {}
        name_lower = self.business_name.lower()
        
        review_indicators = {
            'rating': 0, 'star': 0, 'review': 0, 'testimonial': 0,
            'google review': 0, 'trustpilot': 0, 'yelp': 0, 'angie': 0,
            'tripadvisor': 0, 'facebook review': 0
        }
        
        if self.website_url and self.resp and self.resp.status_code == 200:
            html_lower = self.html.lower()
            for word in review_indicators:
                if word in html_lower:
                    review_indicators[word] = html_lower.count(word)
        
        has_review_section = sum(review_indicators.values()) > 3
        if has_review_section:
            score += 5
            details['has_reviews_on_website'] = True
        else:
            self.issues.append("⚠️ No reviews or testimonials found on website")
        
        score += 5
        details['review_platforms_possible'] = True
        
        score = min(score, 10)
        self.scores['online_reviews'] = score
        self.details['online_reviews'] = details
        return score

    def _check_seo_basics(self):
        score = 0
        details = {}
        
        if not self.website_url or not self.resp or self.resp.status_code != 200:
            self.issues.append("❌ Cannot check SEO — no website")
            self.scores['seo_basics'] = 0
            self.details['seo_basics'] = details
            return 0
        
        html_lower = self.html.lower()
        
        title_tag = re.search(r'<title>(.*?)</title>', html_lower, re.IGNORECASE)
        if title_tag and title_tag.group(1).strip():
            title = title_tag.group(1).strip()
            score += 3
            title_len = len(title)
            if 30 <= title_len <= 60:
                score += 1
        else:
            self.issues.append("⚠️ Missing page title tag (critical for SEO)")
        
        meta_desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html_lower, re.IGNORECASE)
        if meta_desc and meta_desc.group(1).strip():
            score += 2
            if 120 <= len(meta_desc.group(1).strip()) <= 160:
                score += 1
        else:
            self.issues.append("⚠️ Missing meta description tag")
        
        has_h1 = bool(re.search(r'<h1[^>]*>', html_lower))
        if has_h1:
            score += 2
            details['has_h1'] = True
            h1_count = len(re.findall(r'<h1[^>]*>', html_lower))
            if h1_count > 1:
                self.issues.append(f"⚠️ Multiple H1 tags ({h1_count}) — use only one per page")
        else:
            self.issues.append("⚠️ No H1 heading found")
        
        has_h2 = bool(re.search(r'<h2[^>]*>', html_lower))
        if has_h2:
            score += 1
            details['has_h2'] = True
        
        og_tags = sum(1 for k in ['og:title', 'og:description', 'og:image', 'og:url'] if k in html_lower)
        if og_tags >= 3:
            score += 1
            details['open_graph'] = True
        elif og_tags > 0:
            self.issues.append("⚠️ Incomplete Open Graph tags")
        
        twitter_cards = any(k in html_lower for k in ['twitter:card', 'twitter:title', 'twitter:description'])
        if twitter_cards:
            score += 1
            details['twitter_cards'] = True
        
        canonical = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\'](.*?)["\']', html_lower, re.IGNORECASE)
        if canonical:
            score += 1
            details['canonical'] = True
        
        score = min(score, 10)
        self.scores['seo_basics'] = score
        self.details['seo_basics'] = details
        return score

    def _check_contact_accessibility(self):
        score = 0
        details = {}
        
        contact_patterns = {
            'phone': r'(?:\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}',
            'email': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            'address': r'(?:street|road|avenue|drive|boulevard|ln|drive|square|plaza|building|suite|floor|office|unit)',
            'whatsapp': r'(?:whatsapp|wa\.me|wa.me)'
        }
        
        found_contacts = {}
        
        if self.website_url:
            url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
            try:
                resp = requests.get(url, timeout=10)
                html_lower = resp.text.lower()
                
                for contact_type, pattern in contact_patterns.items():
                    matches = re.findall(pattern, html_lower, re.IGNORECASE)
                    if matches:
                        found_contacts[contact_type] = matches[:2]
            except:
                pass
        
        phone_found = 'phone' in found_contacts
        email_found = 'email' in found_contacts
        address_found = 'address' in found_contacts
        whatsapp_found = 'whatsapp' in found_contacts
        
        if phone_found:
            score += 3
            self.wins.append("✅ Phone number found")
        else:
            self.issues.append("⚠️ No phone number listed")
        
        if email_found:
            score += 3
            self.wins.append("✅ Email address found")
        else:
            self.issues.append("⚠️ No email address listed")
        
        if address_found:
            score += 2
            self.wins.append("✅ Physical address mentioned")
        else:
            self.issues.append("⚠️ No physical address listed — reduces trust")
        
        if whatsapp_found:
            score += 1
            self.wins.append("✅ WhatsApp contact available")
        else:
            self.issues.append("⚠️ WhatsApp contact not found — widely used in Nepal")
        
        details['found'] = found_contacts
        
        score = min(score, 10)
        self.scores['contact_accessibility'] = score
        self.details['contact_accessibility'] = details
        return score

    def calculate_total(self):
        self.total_score = sum(self.scores.values())
        return self.total_score
    
    def get_health_status(self):
        score = self.total_score
        if score >= 80:
            return {"status": "Digitally Healthy", "color": "green", "emoji": "🟢", "type": "excellent"}
        elif score >= 60:
            return {"status": "Needs Improvement", "color": "yellow", "emoji": "🟡", "type": "fair"}
        elif score >= 40:
            return {"status": "Seriously Behind", "color": "orange", "emoji": "🟠", "type": "poor"}
        else:
            return {"status": "Digitally Invisible", "color": "red", "emoji": "🔴", "type": "critical"}
    
    def get_category_scores(self):
        return {
            "website_presence": {"score": self.scores.get("website_presence", 0), "max": 20, "label": "Website Presence"},
            "google_business": {"score": self.scores.get("google_business", 0), "max": 20, "label": "Google Business Profile"},
            "social_media": {"score": self.scores.get("social_media", 0), "max": 15, "label": "Social Media Presence"},
            "mobile_friendly": {"score": self.scores.get("mobile_friendly", 0), "max": 15, "label": "Mobile Friendliness"},
            "online_reviews": {"score": self.scores.get("online_reviews", 0), "max": 10, "label": "Online Reviews"},
            "seo_basics": {"score": self.scores.get("seo_basics", 0), "max": 10, "label": "SEO Basics"},
            "contact_accessibility": {"score": self.scores.get("contact_accessibility", 0), "max": 10, "label": "Contact Accessibility"}
        }
    
    def get_report(self):
        return {
            "business_name": self.business_name,
            "website_url": self.website_url,
            "total_score": self.total_score,
            "health_status": self.get_health_status(),
            "category_scores": self.get_category_scores(),
            "issues": self.issues,
            "wins": self.wins,
            "details": self.details
        }
    
    def run_all_checks(self):
        if self.website_url:
            self._fetch_website()
        self.check_website_presence()
        self.check_google_business()
        self.check_social_media()
        self.check_mobile_friendly()
        self.check_online_reviews()
        self.check_seo_basics()
        self.check_contact_accessibility()
        self.calculate_total()
        return self.get_report()


def generate_demo_report(business_name, website_url=None, location="Nepal"):
    """
    Generate a simulated digital health report WITHOUT making HTTP requests.
    Uses text analysis of inputs to estimate scores.
    """
    text_lower = (business_name + ' ' + (website_url or '') + ' ' + location).lower()
    scores = {}
    issues = []
    wins = []
    
    # Website Presence (20)
    ws = 0
    if website_url:
        ws += 10
        wins.append("✅ Website URL provided")
        if website_url.startswith('https://') or '.com.np' in website_url or '.com' in website_url:
            ws += 4
        if len(website_url) > 10:
            ws += 3
        if '.' in website_url:
            ws += 3
    else:
        issues.append("❌ No website URL — critical gap for credibility")
    scores["website_presence"] = {"score": min(ws, 20), "max": 20, "label": "Website Presence", "icon": "🌐"}
    
    # Google Business (20)
    gb = 5
    formal_indicators = ['pvt', 'ltd', 'private', 'limited', 'company', 'store', 'restaurant', 'hotel', 'salon', 'center', 'enterprise']
    if any(w in text_lower for w in formal_indicators):
        gb += 5
        wins.append("✅ Formal business name detected")
    if location and location.lower() != 'nepal':
        gb += 5
    if website_url:
        gb += 3
    if '.' in business_name:
        gb += 2
    if gb < 10:
        issues.append("⚠️ May not have Google Business Profile — essential for local search")
    scores["google_business"] = {"score": min(gb, 20), "max": 20, "label": "Google Business Profile", "icon": "📍"}
    
    # Social Media (15)
    sm = 0
    platforms_found = []
    social_checks = {'facebook': 'Facebook', 'instagram': 'Instagram', 'twitter': 'Twitter',
                     'linkedin': 'LinkedIn', 'youtube': 'YouTube', 'tiktok': 'TikTok'}
    for keyword, name in social_checks.items():
        if keyword in text_lower:
            sm += 5 if keyword == 'facebook' else 3 if keyword in ('instagram', 'twitter') else 2
            platforms_found.append(name)
    if platforms_found:
        wins.append(f"✅ Social media presence: {', '.join(platforms_found)}")
        if len(platforms_found) >= 3:
            sm += 2
    else:
        issues.append("❌ No social media presence detected — this limits reach severely")
        sm = 3
    scores["social_media"] = {"score": min(sm, 15), "max": 15, "label": "Social Media Presence", "icon": "📱"}
    
    # Mobile Friendliness (15)
    mf = 0
    if website_url:
        mf += 6 + 4
        if '.com.np' in website_url:
            mf += 3
        mf += 2
    else:
        issues.append("⚠️ Cannot assess mobile friendliness — no website")
        mf = 4
    scores["mobile_friendly"] = {"score": min(mf, 15), "max": 15, "label": "Mobile Friendliness", "icon": "📲"}
    
    # Online Reviews (10)
    rv = 3
    review_keywords = ['rating', 'review', 'star', 'testimonials', 'google review']
    if any(w in text_lower for w in review_keywords):
        rv += 4
        wins.append("✅ Reviews/testimonials found")
    if location and location.lower() != 'nepal':
        rv += 2
    if rv < 5:
        issues.append("⚠️ No reviews detected — social proof is crucial")
    scores["online_reviews"] = {"score": min(rv, 10), "max": 10, "label": "Online Reviews", "icon": "⭐"}
    
    # SEO Basics (10)
    seo = 0
    if website_url:
        seo += 4 + 2
        if len(website_url) > 15:
            seo += 2
        seo += 2
    else:
        issues.append("❌ Cannot check SEO — no website")
        seo = 1
    scores["seo_basics"] = {"score": min(seo, 10), "max": 10, "label": "SEO Basics", "icon": "🔎"}
    
    # Contact Accessibility (10)
    ca = 0
    contact_words = ['phone', 'mobile', 'call', 'contact', 'email', 'address', 'whatsapp', 'viber']
    found = [w for w in contact_words if w in text_lower]
    if found:
        ca += min(len(found) * 2, 6)
        wins.append(f"✅ Contact methods found: {', '.join(found)}")
    if 'whatsapp' in text_lower:
        ca += 2
    if website_url:
        ca += 2
    if ca < 4:
        issues.append("⚠️ Contact info limited — add phone, email, and WhatsApp")
    scores["contact_accessibility"] = {"score": min(ca, 10), "max": 10, "label": "Contact Accessibility", "icon": "📞"}
    
    if not issues:
        wins.append("✅ Digital presence assessment completed")
    
    total_score = sum(v["score"] for v in scores.values())
    
    if total_score >= 80:
        status = "Digitally Healthy"; emoji = "🟢"; type_ = "excellent"
    elif total_score >= 60:
        status = "Needs Improvement"; emoji = "🟡"; type_ = "fair"
    elif total_score >= 40:
        status = "Seriously Behind"; emoji = "🟠"; type_ = "poor"
    else:
        status = "Digitally Invisible"; emoji = "🔴"; type_ = "critical"
    
    if total_score >= 80:
        summary = f"✨ {business_name} has a strong digital foundation! With a working website and social media presence, you're ahead of most Nepali businesses. Focus on collecting reviews and optimizing your Google Business Profile to reach even more customers."
    elif total_score >= 60:
        summary = f"📈 {business_name} is on the right track but has room to grow. Your website is a good start, but there are gaps in mobile optimization and social media engagement. Prioritize fixing the issues below to improve your digital presence."
    elif total_score >= 40:
        summary = f"🔄 {business_name} has significant digital gaps that need attention. Start with creating a Google Business Profile and claiming social media handles — these are free steps that will immediately increase visibility."
    else:
        summary = f"🚨 {business_name} is currently digitally invisible. You're missing out on thousands of potential customers. Begin with a free Google Business Profile and a simple Facebook page today."
    
    category_scores = {}
    pillar_labels = {
        "website_presence": "Website Presence",
        "google_business": "Google Business Profile",
        "social_media": "Social Media Presence",
        "mobile_friendly": "Mobile Friendliness",
        "online_reviews": "Online Reviews",
        "seo_basics": "SEO Basics",
        "contact_accessibility": "Contact Accessibility"
    }
    for key, v in scores.items():
        category_scores[key] = {"score": v["score"], "max": v["max"], "label": pillar_labels.get(key, key)}
    
    report = {
        "business_name": business_name,
        "website_url": website_url,
        "location": location,
        "total_score": total_score,
        "health_status": {"status": status, "emoji": emoji, "type": type_},
        "category_scores": category_scores,
        "issues": issues,
        "wins": wins,
        "ai_summary": summary,
        "ai_generated": True,
        "generated_by": "Digital Health Checker Engine (Demo)",
        "recommendations": [],
        "roadmap": []
    }
    
    if not website_url:
        report["recommendations"].append({"priority": "Critical", "action": "Create a website (use free tools like Google Sites, Wix, or WordPress)", "impact": "Opens your business to 24/7 global discovery", "cost": "Free – NPR 5,000"})
    if not platforms_found:
        report["recommendations"].append({"priority": "High", "action": "Create Facebook and Instagram business pages", "impact": "Reach 80%+ of Nepal's online population", "cost": "Free"})
    
    report["recommendations"].append({"priority": "High", "action": "Claim and optimize your Google Business Profile", "impact": "Show up in Google Maps and local search results", "cost": "Free"})
    report["recommendations"].append({"priority": "Medium", "action": "Add WhatsApp contact — the most popular messaging app in Nepal", "impact": "Makes it easy for customers to reach you directly", "cost": "Free"})
    report["recommendations"].append({"priority": "Medium", "action": "Address the warning items listed in the Issues section", "impact": "Improves customer trust and conversion rates", "cost": "Varies"})
    report["recommendations"].append({"priority": "Maintenance", "action": "Ask satisfied customers to leave Google reviews", "impact": "Builds social proof and improves local search ranking", "cost": "Free"})
    
    if not website_url or issues:
        report["roadmap"].append({"week": 1, "task": "Create/improve website", "effort": "2-3 hours"})
    if not platforms_found:
        report["roadmap"].append({"week": 1, "task": "Set up Facebook & Instagram pages", "effort": "1-2 hours"})
    
    report["roadmap"].append({"week": 2, "task": "Optimize Google Business Profile with photos & info", "effort": "1 hour"})
    report["roadmap"].append({"week": 2, "task": "Add WhatsApp Business number to all platforms", "effort": "30 min"})
    report["roadmap"].append({"week": 3, "task": "Collect 5+ Google reviews from existing customers", "effort": "1 hour"})
    report["roadmap"].append({"week": 4, "task": "Review progress and re-check digital health score", "effort": "30 min"})
    
    return report


def generate_full_report(business_name, website_url=None, location="Nepal"):
    """Wrapper for backward compatibility"""
    return generate_demo_report(business_name, website_url, location)


if __name__ == "__main__":
    # Test the checker
    checker = DigitalHealthChecker("Khalti", "khalti.com")
    report = checker.run_all_checks()
    print(json.dumps(report, indent=2, ensure_ascii=False))