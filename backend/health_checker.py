import requests
import re
import json
import ssl
import socket
import os
import time
from urllib.parse import urlparse, urljoin
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any

PILLAR_CONFIG = {
    "website_presence": {"max": 20, "weight": 0.20, "label": "Website Presence", "icon": "\U0001f310"},
    "google_business": {"max": 20, "weight": 0.20, "label": "Google Business Profile", "icon": "\U0001f4cd"},
    "social_media": {"max": 15, "weight": 0.15, "label": "Social Media Presence", "icon": "\U0001f4f1"},
    "mobile_friendly": {"max": 15, "weight": 0.15, "label": "Mobile Friendliness", "icon": "\U0001f4f2"},
    "online_reviews": {"max": 10, "weight": 0.10, "label": "Online Reviews", "icon": "\u2b50"},
    "seo_basics": {"max": 10, "weight": 0.10, "label": "SEO Basics", "icon": "\U0001f50d"},
    "contact_accessibility": {"max": 10, "weight": 0.10, "label": "Contact Accessibility", "icon": "\U0001f4de"},
}

class DigitalHealthChecker:
    def __init__(self, business_name: str, website_url: Optional[str] = None):
        self.business_name = business_name.strip()
        self.website_url = website_url.strip() if website_url else None
        self.normalized_name = re.sub(r'[^\w\s]', '', self.business_name.lower()).strip()
        self.scores = {}
        self.details = {}
        self.issues = []
        self.wins = []
        self.recommendations = []
        self.metadata = {}
        self.resp = None
        self.html = ""
        self.final_url = ""
        self.headers = {}
        self.resp_time = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
        })

    def _fetch_website(self):
        url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
        try:
            self.resp = requests.get(url, timeout=10, allow_redirects=True, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            })
            self.final_url = self.resp.url
            self.html = self.resp.text
            self.headers = dict(self.resp.headers)
        except requests.exceptions.Timeout:
            self.resp = None
            self.html = ""
            self.issues.append("Website request timed out (>10s)")
        except requests.exceptions.ConnectionError:
            self.resp = None
            self.html = ""
            self.issues.append("Could not connect to website")
        except Exception as e:
            self.resp = None
            self.html = ""
            self.issues.append(f"Fetch error: {str(e)[:100]}")

    def _check_website_presence(self):
        if not self.website_url:
            self.scores["website_presence"] = 0
            self.details["website_presence"] = {"reachable": False}
            self.issues.append("No website URL provided - critical gap")
            return
        if not self.resp or self.resp.status_code != 200:
            status = self.resp.status_code if self.resp else "unreachable"
            self.scores["website_presence"] = 0
            self.details["website_presence"] = {"reachable": False, "status": status}
            self.issues.append(f"Website unreachable (status: {status})")
            return
        score = 8
        self.wins.append("Website is live and accessible")
        if self.resp.url.startswith('https://'):
            score += 4
        else:
            self.issues.append("Website not using HTTPS")
        content_type = self.resp.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            score += 2
        load_time = self.resp.elapsed.total_seconds() if hasattr(self.resp, 'elapsed') else 0
        if load_time < 1.5:
            self.wins.append("Website loads quickly")
        elif load_time >= 3:
            self.issues.append("Website load time is slow")
        security_headers_found = 0
        for h in ['X-Content-Type-Options', 'X-Frame-Options', 'Strict-Transport-Security', 'Content-Security-Policy']:
            if h.lower() in {k.lower(): v for k, v in self.headers.items()}:
                security_headers_found += 1
        if security_headers_found >= 3:
            self.wins.append("Good security headers found")
        else:
            self.issues.append("Missing security headers")
        score += security_headers_found
        self.scores["website_presence"] = min(score, 20)
        self.details["website_presence"] = {"reachable": True, "https": self.resp.url.startswith('https://'), "load_time": load_time}

    def _check_google_business(self):
        score = 5
        gbp_indicators = ['pvt', 'ltd', 'private', 'limited', 'company', 'store', 'shop',
                          'restaurant', 'hotel', 'salon', 'clinic', 'center', 'centre',
                          'enterprise', 'industries', 'inc', 'llc', 'corp', 'services', 'group']
        if any(ind in self.normalized_name for ind in gbp_indicators):
            score += 5
            self.wins.append("Business name suggests formal registration")
        else:
            self.issues.append("Business name does not indicate formal registration")
        if self.website_url:
            score += 3
        if self.html and 'maps.google.com' in self.html.lower():
            score += 4
            self.wins.append("Google Maps embed detected")
        if self.html and ('LocalBusiness' in self.html or 'localbusiness' in self.html.lower()):
            score += 3
            self.wins.append("LocalBusiness schema markup detected")
        self.scores["google_business"] = min(score, 20)
        self.details["google_business"] = {"score": score}

    def _check_social_media(self):
        social_platforms = {
            'facebook': ['facebook.com', 'fb.com'],
            'instagram': ['instagram.com'],
            'twitter': ['twitter.com', 'x.com'],
            'linkedin': ['linkedin.com'],
            'youtube': ['youtube.com'],
            'tiktok': ['tiktok.com'],
        }
        found = []
        if self.html:
            html_lower = self.html.lower()
            for platform, domains in social_platforms.items():
                for domain in domains:
                    if domain in html_lower:
                        if platform not in found:
                            found.append(platform)
                        break
        score = min(len(found) * 3, 12)
        if found:
            if len(found) >= 4:
                self.wins.append("Strong multi-platform social presence")
        else:
            self.issues.append("No social media presence detected")
            score = 3
        self.scores["social_media"] = min(score, 15)
        self.details["social_media"] = {"platforms_found": found, "social_presence": len(found) > 0}

    def _check_mobile_friendly(self):
        score = 0
        if not self.website_url or not self.resp or self.resp.status_code != 200:
            self.issues.append("No website to check for mobile friendliness")
            self.scores["mobile_friendly"] = 0
            self.details["mobile_friendly"] = {}
            return
        html = self.html.lower()
        viewport = '<meta name="viewport"' in html
        if viewport:
            score += 5
        else:
            self.issues.append("Website not optimized for mobile (no viewport meta)")
        media_queries = '@media' in html
        if media_queries:
            score += 4
            self.wins.append("CSS media queries detected")
        else:
            self.issues.append("No media queries - may not be responsive")
        if 'srcset' in html or '<picture' in html:
            score += 2
        has_touch = any(x in html for x in ['touch-action', 'pointer-events', 'user-select'])
        if has_touch:
            score += 1
        if 'overflow-x: hidden' in html or 'max-width: 100%' in html:
            score += 1
        try:
            mobile_resp = requests.get(self.final_url or self.website_url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15'
            })
            if '<meta name="viewport"' in mobile_resp.text.lower():
                score += 1
        except:
            pass
        if not viewport:
            score = max(0, score - 2)
        self.scores["mobile_friendly"] = min(score, 15)
        self.details["mobile_friendly"] = {"viewport": viewport, "media_queries": media_queries}

    def _check_online_reviews(self):
        score = 3
        review_keywords = ['rating', 'star', 'review', 'testimonial', 'google review', 'trustpilot']
        if self.html:
            html_lower = self.html.lower()
            found_count = sum(1 for w in review_keywords if w in html_lower)
            if found_count >= 2:
                score += 4
                self.wins.append("Reviews or testimonials found on website")
            else:
                self.issues.append("No reviews or testimonials found on website")
        score += 3
        self.scores["online_reviews"] = min(score, 10)
        self.details["online_reviews"] = {"score": score}

    def _check_seo_basics(self):
        score = 0
        if not self.website_url or not self.resp or self.resp.status_code != 200:
            self.issues.append("Cannot check SEO - no website")
            self.scores["seo_basics"] = 0
            self.details["seo_basics"] = {}
            return
        html_lower = self.html.lower()
        title_tag = re.search(r'<title>(.*?)</title>', self.html, re.IGNORECASE)
        if title_tag and title_tag.group(1).strip():
            score += 3
            title_len = len(title_tag.group(1).strip())
            if 30 <= title_len <= 60:
                score += 1
        else:
            self.issues.append("Missing page title tag")
        meta_desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', self.html, re.IGNORECASE)
        if meta_desc and meta_desc.group(1).strip():
            score += 2
            if 120 <= len(meta_desc.group(1).strip()) <= 160:
                score += 1
        else:
            self.issues.append("Missing meta description tag")
        has_h1 = bool(re.search(r'<h1[^>]*>', self.html, re.IGNORECASE))
        if has_h1:
            score += 2
            h1_count = len(re.findall(r'<h1[^>]*>', self.html, re.IGNORECASE))
            if h1_count > 1:
                self.issues.append(f"Multiple H1 tags ({h1_count})")
        else:
            self.issues.append("No H1 heading found")
        has_h2 = bool(re.search(r'<h2[^>]*>', self.html, re.IGNORECASE))
        if has_h2:
            score += 1
        og_tags = sum(1 for k in ['og:title', 'og:description', 'og:image', 'og:url'] if k in html_lower)
        if og_tags >= 3:
            score += 1
        if any(k in html_lower for k in ['twitter:card', 'twitter:title', 'twitter:description']):
            score += 1
        canonical = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\'](.*?)["\']', self.html, re.IGNORECASE)
        if canonical:
            score += 1
        self.scores["seo_basics"] = min(score, 10)
        self.details["seo_basics"] = {"title": bool(title_tag), "description": bool(meta_desc), "h1": has_h1}

    def _check_contact_accessibility(self):
        score = 0
        contact_patterns = {
            'phone': r'(?:\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}',
            'email': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            'address': r'(?:street|road|avenue|drive|boulevard|ln|drive|square|plaza|building|suite|floor|office|unit)',
            'whatsapp': r'(?:whatsapp|wa\.me|wa.me)'
        }
        found_contacts = {}
        if self.html:
            for contact_type, pattern in contact_patterns.items():
                matches = re.findall(pattern, self.html, re.IGNORECASE)
                if matches:
                    found_contacts[contact_type] = matches[:2]
        if 'phone' in found_contacts:
            score += 3
            self.wins.append("Phone number found")
        else:
            self.issues.append("No phone number listed")
        if 'email' in found_contacts:
            score += 3
            self.wins.append("Email address found")
        else:
            self.issues.append("No email address listed")
        if 'address' in found_contacts:
            score += 2
            self.wins.append("Physical address mentioned")
        else:
            self.issues.append("No physical address listed")
        if 'whatsapp' in found_contacts:
            score += 1
            self.wins.append("WhatsApp contact available")
        else:
            self.issues.append("WhatsApp contact not found")
        self.scores["contact_accessibility"] = min(score, 10)
        self.details["contact_accessibility"] = {"found": found_contacts}

    def get_health_status(self, total_score):
        if total_score >= 80:
            return {"status": "Digitally Healthy", "color": "green", "emoji": "\U0001f7e2", "type": "excellent", "label": "Excellent"}
        elif total_score >= 60:
            return {"status": "Needs Improvement", "color": "yellow", "emoji": "\U0001f7e1", "type": "fair", "label": "Good"}
        elif total_score >= 40:
            return {"status": "Seriously Behind", "color": "orange", "emoji": "\U0001f7e0", "type": "poor", "label": "Needs Work"}
        else:
            return {"status": "Digitally Invisible", "color": "red", "emoji": "\U0001f534", "type": "critical", "label": "Critical"}

    def get_category_scores(self):
        result = {}
        for key, cfg in PILLAR_CONFIG.items():
            result[key] = {"score": self.scores.get(key, 0), "max": cfg["max"], "label": cfg["label"]}
        return result

    def run_all_checks(self) -> Dict[str, Any]:
        if self.website_url:
            self._fetch_website()
        self._check_website_presence()
        self._check_google_business()
        self._check_social_media()
        self._check_mobile_friendly()
        self._check_online_reviews()
        self._check_seo_basics()
        self._check_contact_accessibility()
        total_score = sum(self.scores.values())
        health_status = self.get_health_status(total_score)
        return {
            "business_name": self.business_name,
            "website_url": self.website_url,
            "total_score": total_score,
            "health_status": health_status,
            "category_scores": self.get_category_scores(),
            "issues": self.issues,
            "wins": self.wins,
            "details": self.details,
        }

def generate_demo_report(business_name, website_url=None, location="Nepal"):
    text_lower = (business_name + ' ' + (website_url or '') + ' ' + location).lower()
    scores = {}
    issues = []
    wins = []
    ws = 0
    if website_url:
        ws += 10
        wins.append("Website URL provided")
        if website_url.startswith('https://') or '.com' in website_url:
            ws += 4
        if len(website_url) > 10:
            ws += 3
        ws += 3
    else:
        issues.append("No website URL - critical gap")
    scores["website_presence"] = {"score": min(ws, 20), "max": 20, "label": "Website Presence"}
    gb = 5
    formal_indicators = ['pvt', 'ltd', 'private', 'limited', 'company', 'store', 'restaurant', 'hotel', 'salon', 'center', 'enterprise']
    if any(w in text_lower for w in formal_indicators):
        gb += 5
        wins.append("Formal business name detected")
    if website_url:
        gb += 5
    if gb < 10:
        issues.append("May not have Google Business Profile")
    scores["google_business"] = {"score": min(gb, 20), "max": 20, "label": "Google Business Profile"}
    sm = 0
    platforms_found = []
    social_checks = {'facebook': 'Facebook', 'instagram': 'Instagram', 'twitter': 'Twitter', 'linkedin': 'LinkedIn', 'youtube': 'YouTube', 'tiktok': 'TikTok'}
    for keyword, name in social_checks.items():
        if keyword in text_lower:
            sm += 5 if keyword == 'facebook' else 3
            platforms_found.append(name)
    if platforms_found:
        wins.append(f"Social media presence: {', '.join(platforms_found)}")
        if len(platforms_found) >= 3:
            sm += 2
    else:
        issues.append("No social media presence detected")
        sm = 3
    scores["social_media"] = {"score": min(sm, 15), "max": 15, "label": "Social Media Presence"}
    mf = 6
    if website_url:
        mf += 6
        mf += 3
    else:
        issues.append("Cannot assess mobile friendliness")
        mf = 4
    scores["mobile_friendly"] = {"score": min(mf, 15), "max": 15, "label": "Mobile Friendliness"}
    rv = 3
    review_keywords = ['rating', 'review', 'star', 'testimonials']
    if any(w in text_lower for w in review_keywords):
        rv += 4
        wins.append("Reviews/testimonials found")
    if rv < 5:
        issues.append("No reviews detected")
    scores["online_reviews"] = {"score": min(rv, 10), "max": 10, "label": "Online Reviews"}
    seo = 0
    if website_url:
        seo += 4 + 2
        if len(website_url) > 15:
            seo += 2
        seo += 2
    else:
        issues.append("Cannot check SEO")
        seo = 1
    scores["seo_basics"] = {"score": min(seo, 10), "max": 10, "label": "SEO Basics"}
    ca = 0
    contact_words = ['phone', 'mobile', 'call', 'contact', 'email', 'address', 'whatsapp', 'viber']
    found = [w for w in contact_words if w in text_lower]
    if found:
        ca += min(len(found) * 2, 6)
        wins.append(f"Contact methods found: {', '.join(found)}")
    if 'whatsapp' in text_lower:
        ca += 2
    if website_url:
        ca += 2
    if ca < 4:
        issues.append("Contact info limited")
    scores["contact_accessibility"] = {"score": min(ca, 10), "max": 10, "label": "Contact Accessibility"}
    total_score = sum(v["score"] for v in scores.values())
    if total_score >= 80:
        status = "Digitally Healthy"; emoji = "\U0001f7e2"; type_ = "excellent"
    elif total_score >= 60:
        status = "Needs Improvement"; emoji = "\U0001f7e1"; type_ = "fair"
    elif total_score >= 40:
        status = "Seriously Behind"; emoji = "\U0001f7e0"; type_ = "poor"
    else:
        status = "Digitally Invisible"; emoji = "\U0001f534"; type_ = "critical"
    if total_score >= 80:
        summary = f"\u2728 {business_name} has a strong digital foundation!"
    elif total_score >= 60:
        summary = f"\U0001f4c8 {business_name} is on the right track but has room to grow."
    elif total_score >= 40:
        summary = f"\U0001f504 {business_name} has significant digital gaps."
    else:
        summary = f"\U0001f6a8 {business_name} is currently digitally invisible."
    return {
        "business_name": business_name,
        "website_url": website_url,
        "total_score": total_score,
        "health_status": {"status": status, "emoji": emoji, "type": type_},
        "category_scores": scores,
        "issues": issues,
        "wins": wins,
        "ai_summary": summary,
        "details": {},
        "recommendations": [],
        "roadmap": []
    }

if __name__ == "__main__":
    checker = DigitalHealthChecker("Khalti", "khalti.com")
    report = checker.run_all_checks()
    print(json.dumps(report, indent=2, ensure_ascii=False))
