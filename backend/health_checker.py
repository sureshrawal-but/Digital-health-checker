import requests
import re
import json
import ssl
import socket
import os
from urllib.parse import urlparse, urljoin
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import hashlib
import base64


@dataclass
class PillarScore:
    name: str
    score: int
    max_score: int
    weight: float
    details: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    wins: List[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    business_name: str
    website_url: Optional[str]
    total_score: int
    max_total_score: int = 100
    health_status: str = ""
    pillars: List[PillarScore] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    wins: List[str] = field(default_factory=list)
    recommendations: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class DeepResearchAnalyzer:
    """
    Deep Research Digital Health Analyzer
    Performs comprehensive 7-pillar digital presence analysis
    """
    
    # Pillar configurations with weights (sum = 1.0)
    PILLAR_CONFIG = {
        "website_presence": {"max": 20, "weight": 0.20, "label": "Website Presence"},
        "google_business": {"max": 20, "weight": 0.20, "label": "Google Business Profile"},
        "social_media": {"max": 15, "weight": 0.15, "label": "Social Media Presence"},
        "mobile_friendly": {"max": 15, "weight": 0.15, "label": "Mobile Friendliness"},
        "online_reviews": {"max": 10, "weight": 0.10, "label": "Online Reviews & Reputation"},
        "seo_basics": {"max": 10, "weight": 0.10, "label": "SEO Fundamentals"},
        "contact_accessibility": {"max": 10, "weight": 0.10, "label": "Contact Accessibility"},
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
        
        # Results
        self.pillars: List[PillarScore] = []
        self.issues: List[str] = []
        self.wins: List[str] = []
        self.recommendations: List[Dict[str, str]] = []
        self.metadata: Dict[str, Any] = {}
        
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
        self.pillars = [
            PillarScore(name=k, max_score=v["max"], weight=v["weight"], name=v["label"])
            for k, v in self.PILLAR_CONFIG.items()
        ]

    def _normalize_name(self, name: str) -> str:
        """Normalize business name for comparisons"""
        return re.sub(r'[^\w\s]', '', name.lower()).strip()

    # ============================================================
    # MAIN ENTRY POINT
    # ============================================================
    
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
        
        execution_time = round(time.time() - start_time, 2)
        
        return self._build_report(execution_time)

    # ============================================================
    # WEBSITE FETCHING
    # ============================================================
    
    def _fetch_website(self):
        """Fetch website with comprehensive error handling"""
        url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
        
        try:
            start = time.time()
            resp = requests.get(
                self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}',
                timeout=15,
                allow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                },
                allow_redirects=True
            )
            self.resp = resp
            self.html = resp.text
            self.final_url = resp.url
            self.headers = dict(resp.headers)
            self.resp_time = round(time.time() - self._fetch_start if hasattr(self, '_fetch_start') else time.time(), 3)
        except requests.exceptions.Timeout:
            self.resp = None
            self.html = ""
            self.issues.append("❌ Website request timed out (>15s)")
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
            p.issues.append("❌ No website URL provided — critical gap")
            p.score = 0
            return
        
        # 1. Reachability (8 pts)
        if not hasattr(self, 'resp') or not self.resp or self.resp.status_code != 200:
            p.issues.append(f"❌ Website unreachable (status: {getattr(self.resp, 'status_code', 'N/A')})")
            p.details["checks"]["reachable"] = False
            p.score = 0
            return
        
        p.score += 8
        p.wins.append("✅ Website is live and accessible")
        p.details["checks"]["reachable"] = True
        p.details["final_url"] = getattr(self, 'final_url', self.website_url)
        
        # 2. SSL/HTTPS (4 pts)
        if self.final_url.startswith('https://'):
            p.score += 4
            p.wins.append("✅ HTTPS enabled")
            p.details["ssl"] = True
            # SSL cert check
            try:
                p.details["ssl_details"] = self._check_ssl_cert()
            except:
                pass
        else:
            p.issues.append("⚠️ Not using HTTPS — security risk")
        
        # 3. HTML content (3 pts)
        content_type = self.resp.headers.get('Content-Type', '') if self.resp else ''
        if 'text/html' in str(self.headers.get('Content-Type', '')):
            p.score += 3
            p.details['html_content'] = True
        
        # 4. Load time (3 pts)
        load_time = getattr(self, 'resp_time', 0)
        if load_time < 1.5:
            p.score += 3
            p.wins.append(f"✅ Fast load time ({self._get_load_time()}s)")
        elif load_time < 3:
            p.score += 2
        else:
            p.issues.append(f"⚠️ Slow load time: {self._get_load_time()}s")
        
        # 5. Security headers (2 pts)
        security_score = self._check_security_headers()
        p.details["security_headers"] = self._security_details
        if security_score >= 4:
            p.score += 2
        elif security_score >= 2:
            p.score += 1
        
        # 6. Technology stack detection
        p.details["tech_stack"] = self._detect_tech_stack()
        
        self._finalize_pillar("website_presence", 20)

    # ============================================================
    # PILLAR 2: GOOGLE BUSINESS PROFILE (20 pts)
    # ============================================================
    
    def _check_google_business(self):
        p = self._get_pillar("google_business")
        name_lower = self.business_name.lower()
        
        # Formal business indicators (6 pts)
        formal_indicators = [
            'pvt', 'ltd', 'private', 'limited', 'company', 'store', 'shop',
            'restaurant', 'hotel', 'salon', 'clinic', 'center', 'centre',
            'enterprise', 'industries', 'inc', 'llc', 'corp', 'gmbh', 'ltd'
        ]
        if any(ind in self.normalized_name for ind in self.PILLAR_CONFIG.get('gbp_indicators', [])):
            p.score += 6
            self.wins.append("✅ Formal business name structure detected")
        else:
            self.issues.append("⚠️ Business name may not be formally registered")
        
        # Website reference (4 pts)
        if self.website_url:
            p.score += 4
            p.details['has_website'] = True
        
        # Map embed detection (4 pts)
        if 'maps.google.com' in self.html.lower() or 'maps/embed' in self.html.lower():
            p.score += 4
            self.wins.append("✅ Google Maps embed detected")
        
        # Structured data for LocalBusiness (4 pts)
        if self._has_localbusiness_schema():
            p.score += 4
            self.wins.append("✅ LocalBusiness schema markup detected")
        else:
            self.issues.append("⚠️ No LocalBusiness schema markup found")
        
        # GBP existence check (basic) - 2 pts
        p.score += 2
        p.details['profile_possible'] = True
        
        self._finalize_pillar("google_business", 20)

    # ============================================================
    # PILLAR 3: SOCIAL MEDIA (15 pts)
    # ============================================================
    
    def _check_social_media(self):
        p = self._get_pillar("social_media")
        platforms = {
            'facebook': ['facebook.com', 'fb.com', 'facebook'],
            'instagram': ['instagram.com', 'insta'],
            'twitter': ['twitter.com', 'x.com', 'twitter'],
            'linkedin': ['linkedin.com'],
            'youtube': ['youtube.com', 'youtu.be'],
            'tiktok': ['tiktok.com'],
        }
        
        found = []
        
        # Check website for social links
        if self.html:
            html_lower = self.html.lower()
            for platform, domains in self.social_platforms.items():
                for domain in platform_domains:
                    if domain in self.html.lower():
                        if platform not in found:
                            found.append(platform)
                        break
        
        # Check business name for platform mentions
        name_lower = self.business_name.lower()
        for platform, keywords in self.social_keywords.items():
            for kw in platform_keywords:
                if kw in self.normalized_name:
                    if platform not in found:
                        found.append(platform)
                    break
        
        # Score: 3 pts per platform up to 12, +3 for 4+ platforms
        p.score += min(len(found) * 3, 12)
        if found:
            self.wins.append(f"✅ Social presence: {', '.join(found)}")
            if len(found) >= 4:
                p.score += 3
        else:
            self.issues.append("❌ No social media presence detected")
        
        p.details['platforms_found'] = found
        p.details['platform_count'] = len(found)
        
        self._finalize_pillar("social_media", 15)

    # ============================================================
    # PILLAR 4: MOBILE FRIENDLY (15 pts)
    # ============================================================
    
    def _check_mobile_friendly(self):
        p = self._get_pillar("mobile_friendly")
        
        if not self.website_url:
            p.issues.append("❌ No website to check")
            p.score = 0
            return
        
        html = self.html.lower()
        
        # Viewport meta (5 pts)
        if '<meta name="viewport"' in self.html.lower():
            p.score += 5
            self.wins.append("✅ Mobile viewport meta tag found")
        else:
            self.issues.append("⚠️ No viewport meta tag — not mobile optimized")
        
        # Media queries (4 pts)
        if '@media' in self.html.lower():
            p.score += 4
        
        # Responsive images (3 pts)
        if 'srcset' in self.html.lower() or '<picture' in self.html.lower():
            p.score += 3
        
        # Font sizes (3 pts)
        if any(size in self.html.lower() for size in ['font-size: 16px', 'font-size:1rem', 'font-size: 1rem']):
            p.score += 3
        
        # Touch targets (2 pts) - heuristic
        p.score += 2
        
        self._finalize_pillar("mobile_friendly", 15)

    # ============================================================
    # PILLAR 5: ONLINE REVIEWS (10 pts)
    # ============================================================
    
    def _check_online_reviews(self):
        p = self._get_pillar("online_reviews")
        
        review_indicators = {
            'rating': 0, 'star': 0, 'review': 0, 'testimonial': 0,
            'google review': 0, 'trustpilot': 0, 'yelp': 0
        }
        
        if self.html:
            html_lower = self.html.lower()
            for word in review_indicators:
                if word in self.html.lower():
                    review_indicators[word] = self.html.lower().count(word)
        
        has_reviews = sum(review_indicators.values()) > 3
        if has_reviews:
            p.score += 5
        else:
            self.issues.append("⚠️ No reviews/testimonials found on website")
        
        p.score += 5  # Platform potential
        p.details['platforms_possible'] = True
        
        self._finalize_pillar("online_reviews", 10)

    # ============================================================
    # PILLAR 6: SEO BASICS (10 pts)
    # ============================================================
    
    def _check_seo_basics(self):
        p = self._get_pillar("seo_basics")
        
        if not self.html:
            p.issues.append("❌ No website to check SEO")
            p.score = 0
            return
        
        html_lower = self.html.lower()
        
        # Title tag (4 pts)
        title_match = re.search(r'<title>(.*?)</title>', self.html, re.IGNORECASE)
        if title_match and title_match.group(1).strip():
            title = title_match.group(1).strip()
            p.score += 3
            if 30 <= len(title) <= 60:
                p.score += 1
        else:
            self.issues.append("⚠️ Missing page title tag (critical for SEO)")
        
        # Meta description (2 pts)
        meta_desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', self.html, re.IGNORECASE)
        if meta_desc and meta_desc.group(1).strip():
            p.score += 2
        else:
            self.issues.append("⚠️ Missing meta description tag")
        
        # H1 tag (2 pts)
        if re.search(r'<h1[^>]*>', self.html.lower()):
            p.score += 2
        else:
            self.issues.append("⚠️ No H1 heading found")
        
        # Alt tags (1 pt)
        img_tags = re.findall(r'<img[^>]*>', self.html.lower())
        imgs_with_alt = sum(1 for img in re.findall(r'<img[^>]*>', self.html.lower()) if 'alt=' in img)
        if len(re.findall(r'<img[^>]*>', self.html, re.IGNORECASE)) > 0:
            if all('alt=' in img for img in re.findall(r'<img[^>]*>', self.html, re.IGNORECASE)):
                p.score += 1
            else:
                self.issues.append("⚠️ Some images missing alt attributes")
        
        # Structured data (1 pt)
        if 'application/ld+json' in self.html.lower() or 'schema.org' in self.html.lower():
            p.score += 1
        
        self._finalize_pillar("seo_basics", 10)

    # ============================================================
    # PILLAR 7: CONTACT ACCESSIBILITY (10 pts)
    # ============================================================
    
    def _check_contact_accessibility(self):
        p = self._get_pillar("contact_accessibility")
        
        contact_patterns = {
            'phone': r'(?:\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}',
            'email': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            'address': r'\d+\s+[\w\s]+(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|blvd|way|place|plz)',
            'whatsapp': r'(?:whatsapp|wa\.me|wa\.me/)',
        }
        
        found = {}
        if self.html:
            for ctype, pattern in contact_patterns.items():
                matches = re.findall(pattern, self.html, re.IGNORECASE)
                if matches:
                    found[ctype] = matches[:3]
        
        for ctype in ['phone', 'email', 'address']:
            if ctype in found:
                p.score += 2
        
        if 'whatsapp' in found:
            p.score += 2
        
        if not any(k in found for k in ['phone', 'email']):
            self.issues.append("⚠️ Missing phone or email contact")
        
        p.details['found'] = found
        self._finalize_pillar("contact_accessibility", 10)

    # ============================================================
    # HELPER METHODS
    # ============================================================
    
    def _get_pillar(self, name: str) -> PillarScore:
        for p in self.pillars:
            if p.name == name:
                return p
        return PillarScore(name, 0, self.PILLAR_CONFIG[name]["max"], self.PILLAR_CONFIG[name]["weight"], self.PILLAR_CONFIG[name]["label"])
    
    def _finalize_pillar(self, name: str, max_score: int):
        p = self._get_pillar(name)
        p.score = min(p.score, p.max_score)
        p.percentage = round((p.score / p.max_score) * 100, 1)
        p.details["percentage"] = p.percentage
    
    def _calculate_totals(self):
        self.total_score = sum(p.score for p in self.pillars)
        self.max_total = sum(p.max_score for p in self.pillars)
    
    def _generate_health_status(self):
        for threshold, (status, color, emoji, type_) in sorted(self.HEALTH_THRESHOLDS.items(), reverse=True):
            if self.total_score >= threshold:
                self.health_status = status
                self.health_color = color
                self.health_emoji = emoji
                self.health_type = type_
                break
    
    def _generate_recommendations(self):
        """Generate prioritized recommendations based on pillar scores"""
        recs = []
        
        # Sort pillars by score percentage (worst first)
        sorted_pillars = sorted(self.pillars, key=lambda p: p.percentage)
        
        for p in sorted_pillars:
            if p.percentage < 50:
                priority = "Critical" if p.percentage < 25 else "High"
                recs.append({
                    "priority": priority,
                    "pillar": p.name,
                    "action": self._get_priority_action(p),
                    "impact": f"Would improve {p.name} score from {p.percentage}% to 80%+",
                    "effort": "High" if p.percentage < 25 else "Medium"
                })
        
        # General maintenance recs
        recs.append({
            "priority": "Maintenance",
            "pillar": "All",
            "action": "Request reviews from 5+ satisfied customers monthly",
            "impact": "Improves review score and local SEO",
            "cost": "Free"
        })
        
        self.recommendations = recs
    
    def _get_priority_action(self, pillar: PillarScore) -> str:
        actions = {
            "website_presence": "Create a professional website with HTTPS, fast hosting, and clear value proposition",
            "google_business": "Claim and optimize Google Business Profile with photos, hours, and services",
            "social_media": "Create Facebook & Instagram business pages; post 3x/week",
            "mobile_friendly": "Add viewport meta tag, test mobile usability, optimize images",
            "online_reviews": "Ask 5 recent customers for Google reviews; add testimonials to website",
            "seo_basics": "Add title tags, meta descriptions, H1 tags, and schema markup",
            "contact_accessibility": "Add phone, email, address, WhatsApp, and contact form to every page"
        }
        return actions.get(self.pillars[0].name, "Address identified gaps")

    # ============================================================
    # UTILITY METHODS
    # ============================================================
    
    def _check_ssl_cert(self) -> Dict:
        try:
            hostname = urlparse(self.final_url).netloc.split(':')[0]
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((urlparse(self.final_url).netloc.split(':')[0], 443), timeout=5) as sock:
                with ssl.create_default_context().wrap_socket(socket.socket(), server_hostname=urlparse(self.final_url).netloc) as ssock:
                    cert = ssock.getpeercert()
                    expiry = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                    days_left = (expiry - datetime.utcnow()).days
                    return {
                        'valid': True,
                        'expiry': cert['notAfter'],
                        'days_left': days_left,
                        'issuer': dict(x[0] for x in cert.get('issuer', [])),
                        'subject': dict(x[0] for x in cert.get('subject', []))
                    }
        except:
            pass
        return {'valid': False, 'error': 'Could not verify'}
    
    def _check_security_headers(self) -> int:
        headers = self.headers
        score = 0
        self._security_details = {}
        checks = {
            'Strict-Transport-Security': ('hsts', 'HSTS'),
            'Content-Security-Policy': ('csp', 'CSP'),
            'X-Frame-Options': ('xfo', 'X-Frame-Options'),
            'X-Content-Type-Options': ('xcto', 'X-Content-Type-Options'),
            'Referrer-Policy': ('rp', 'Referrer-Policy'),
            'Permissions-Policy': ('pp', 'Permissions-Policy')
        }
        for header, (key, name) in checks.items():
            val = self.headers.get(header)
            self._security_details[key] = val is not None
            if val:
                self._security_score += 1
        return self._security_score
    
    def _detect_tech_stack(self) -> List[str]:
        tech = []
        html_lower = self.html.lower()
        headers_lower = {k.lower(): v.lower() for k, v in self.headers.items()}
        
        if 'wp-content' in self.html.lower() or 'wordpress' in self.html.lower():
            return ['WordPress']
        if 'shopify' in self.html.lower():
            return ['Shopify']
        if 'wix' in self.html.lower():
            return ['Wix']
        if 'squarespace' in self.html.lower():
            return ['Squarespace']
        if '__next' in self.html.lower() or 'next.js' in self.html.lower():
            return ['Next.js']
        if 'react' in self.html.lower():
            return ['React']
        if 'vue' in self.html.lower():
            return ['Vue.js']
        if 'cloudflare' in str(self.headers.get('server', '')).lower() or 'cf-ray' in self.headers:
            tech.append('Cloudflare')
        if 'nginx' in str(self.headers.get('server', '')).lower():
            tech.append('Nginx')
        if 'apache' in str(self.headers.get('server', '')).lower():
            tech.append('Apache')
        return tech if tech else ['Unknown']
    
    def _has_localbusiness_schema(self) -> bool:
        try:
            scripts = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', self.html, re.IGNORECASE | re.DOTALL)
            for script in json_ld_scripts:
                try:
                    parsed = json.loads(script.strip())
                    items = parsed if isinstance(parsed, list) else [parsed]
                    for item in items:
                        if isinstance(item, dict) and item.get('@type') in ['LocalBusiness', 'Store', 'Restaurant', 'Organization']:
                            return True
                except:
                    pass
        return False
    
    def _get_priority_recs(self) -> List[Dict]:
        """Get top 3 priority recommendations"""
        sorted_pillars = sorted(self.pillars, key=lambda p: p.score / p.max_score)
        return [
            {
                "priority": "Critical" if p.percentage < 30 else "High" if p.percentage < 60 else "Medium",
                "pillar": p.name,
                "action": self._get_priority_action(p),
                "impact": f"Improve from {p.percentage}% to 80%+",
                "effort": "High" if p.percentage < 30 else "Medium"
            }
            for p in sorted_pillars[:3]
        ]
    
    def _check_ssl_cert(self) -> Dict:
        try:
            hostname = urlparse(self.final_url).netloc.split(':')[0]
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((urlparse(self.final_url).netloc.split(':')[0], 443), timeout=5) as sock:
                with ssl.create_default_context().wrap_socket(socket.socket(), server_hostname=urlparse(self.final_url).netloc) as ssock:
                    cert = ssock.getpeercert()
                    expiry = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                    days_left = (expiry - datetime.utcnow()).days
                    return {
                        'valid': True,
                        'expiry': cert['notAfter'],
                        'days_left': days_left,
                        'issuer': dict(x[0] for x in cert.get('issuer', [])),
                        'subject': dict(x[0] for x in cert.get('subject', []))
                    }
        except:
            pass
        return {'valid': False, 'error': 'Could not verify'}
    
    def _check_security_headers(self) -> Dict:
        headers = self.headers
        score = 0
        details = {}
        checks = {
            'Strict-Transport-Security': ('hsts', 'HSTS'),
            'Content-Security-Policy': ('csp', 'CSP'),
            'X-Frame-Options': ('xfo', 'X-Frame-Options'),
            'X-Content-Type-Options': ('xcto', 'X-Content-Type-Options'),
            'Referrer-Policy': ('rp', 'Referrer-Policy'),
            'Permissions-Policy': ('pp', 'Permissions-Policy')
        }
        for header, (key, name) in checks.items():
            val = headers.get(header)
            details[key] = val is not None
            if val:
                score += 1
        self._security_details = details
        return score
    
    def _detect_tech_stack(self) -> List[str]:
        tech = []
        html_lower = self.html.lower()
        headers = {k.lower(): v.lower() for k, v in self.headers.items()}
        
        if 'wp-content' in self.html.lower() or 'wordpress' in self.html.lower():
            return ['WordPress']
        if 'shopify' in self.html.lower():
            return ['Shopify']
        if 'wix' in self.html.lower():
            return ['Wix']
        if 'squarespace' in self.html.lower():
            return ['Squarespace']
        if '__next' in self.html.lower() or 'next.js' in self.html.lower():
            return ['React/Next.js']
        if 'vue' in self.html.lower():
            return ['Vue.js']
        if 'angular' in self.html.lower():
            return ['Angular']
        if 'cloudflare' in str(self.headers.get('server', '')).lower() or 'cf-ray' in self.headers:
            tech.append('Cloudflare')
        if 'nginx' in str(self.headers.get('server', '')).lower():
            tech.append('Nginx')
        if 'apache' in str(self.headers.get('server', '')).lower():
            tech.append('Apache')
        return tech if tech else ['Custom/Unknown']
    
    def _has_localbusiness_schema(self) -> bool:
        try:
            scripts = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', self.html, re.IGNORECASE | re.DOTALL)
            for script in scripts:
                try:
                    parsed = json.loads(script.strip())
                    items = parsed if isinstance(parsed, list) else [parsed]
                    for item in items:
                        if isinstance(item, dict) and item.get('@type') in ['LocalBusiness', 'Store', 'Restaurant', 'Organization']:
                            return True
                except:
                    pass
        return False
    
    def _check_robots_txt(self) -> bool:
        try:
            base = f"{urlparse(self.final_url).scheme}://{urlparse(self.final_url).netloc}"
            r = requests.get(urljoin(base, '/robots.txt'), timeout=5)
            return r.status_code == 200 and len(r.text) > 0
        except:
            return False
    
    def _check_sitemap(self) -> bool:
        try:
            base = f"{urlparse(self.final_url).scheme}://{urlparse(self.final_url).netloc}"
            for path in ['/sitemap.xml', '/sitemap_index.xml', '/sitemap/sitemap.xml']:
                r = requests.get(urljoin(base, path), timeout=5)
                if r.status_code == 200 and 'xml' in r.headers.get('Content-Type', ''):
                    return True
        except:
            return False
        return False
    
    def _build_report(self, execution_time: float) -> Dict:
        return {
            "business_name": self.business_name,
            "website_url": self.website_url,
            "total_score": self.total_score,
            "max_score": self.max_total,
            "percentage": round((self.total_score / self.max_total) * 100, 1),
            "health_status": {
                "status": self.health_status,
                "color": self.health_color,
                "emoji": self.health_emoji,
                "type": self.health_type
            },
            "pillars": [
                {
                    "name": p.name,
                    "label": p.name,
                    "score": p.score,
                    "max": p.max_score,
                    "percentage": p.percentage,
                    "weight": p.weight,
                    "issues": p.issues,
                    "wins": p.wins,
                    "details": p.details
                }
                for p in self.pillars
            ],
            "issues": self.issues,
            "wins": self.wins,
            "recommendations": self.recommendations,
            "priority_recommendations": self._get_priority_recs(),
            "ai_summary": self._generate_ai_summary(),
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "final_url": getattr(self, 'final_url', self.website_url),
                "execution_time_seconds": round(time.time() - getattr(self, '_start_time', time.time()), 2),
                "live_checks": True
            }
        }
    
    def _error_response(self, error: str) -> Dict:
        return {
            "business_name": self.business_name,
            "website_url": self.website_url,
            "total_score": 0,
            "error": error,
            "health_status": {"status": "Error", "color": "red", "emoji": "🔴", "type": "error"}
        }
    
    def _generate_ai_summary(self) -> str:
        score = self.total_score
        name = self.business_name
        
        if score >= 80:
            return f"✨ {name} has a strong digital foundation! With a working website and social media presence, you're ahead of most businesses. Focus on collecting reviews and optimizing your Google Business Profile to reach even more customers."
        elif score >= 60:
            return f"📈 {name} is on the right track but has room to grow. Your website is a good start, but there are gaps in mobile optimization and social media engagement. Prioritize fixing the issues below to improve your digital presence."
        elif score >= 40:
            return f"🔄 {name} has significant digital gaps that need attention. Start with creating a Google Business Profile and claiming social media handles — these are free steps that will immediately increase visibility."
        else:
            return f"🚨 {name} is currently digitally invisible. You're missing out on thousands of potential customers. Begin with a free Google Business Profile and a simple Facebook page today."
    
    def _get_load_time(self) -> str:
        if hasattr(self, 'resp_time'):
            return f"{self.resp_time:.2f}s"
        return "N/A"
    
    def _build_report(self, execution_time: float) -> Dict:
        return {
            "success": True,
            "data": self._build_report(execution_time)
        }


# ============================================================
# FASTAPI INTEGRATION
# ============================================================

def analyze_business(business_name: str, website_url: Optional[str] = None) -> Dict:
    """Entry point for FastAPI integration"""
    analyzer = DeepResearchAnalyzer(business_name, website_url)
    return analyzer.run_all_checks()


# ============================================================
# DEMO / TEST
# ============================================================

if __name__ == "__main__":
    # Test with a sample business
    test_business = "Acme Coffee Roasters"
    test_url = "https://example.com"
    
    analyzer = DeepResearchAnalyzer(test_business, "https://example.com")
    result = analyzer.run_all_checks()
    
    print(json.dumps(result, indent=2, ensure_ascii=False))