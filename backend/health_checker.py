import requests
import re
import json
from urllib.parse import urlparse

class DigitalHealthChecker:
    def __init__(self, business_name, website_url=None):
        self.business_name = business_name
        self.website_url = website_url
        self.scores = {}
        self.issues = []
        self.wins = []
        self.details = {}
        self.total_score = 0

    def run_all_checks(self):
        self.check_website_presence()
        self.check_google_business()
        self.check_social_media()
        self.check_mobile_friendly()
        self.check_online_reviews()
        self.check_seo_basics()
        self.check_contact_accessibility()
        self.calculate_total()
        return self.get_report()

    def check_website_presence(self):
        score = 0
        details = {}

        if self.website_url:
            url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
            try:
                resp = requests.get(url, timeout=10, allow_redirects=True)
                if resp.status_code == 200:
                    score += 10
                    details['reachable'] = True
                    self.wins.append("✅ Website is live and accessible")

                    final_url = resp.url
                    if final_url.startswith('https://'):
                        score += 4
                        details['ssl'] = True
                        self.wins.append("✅ SSL certificate present (HTTPS)")
                    else:
                        self.issues.append("⚠️ Website not using HTTPS (security risk)")

                    content_type = resp.headers.get('Content-Type', '')
                    if 'text/html' in content_type:
                        score += 3
                        details['html'] = True

                    load_time_ok = resp.elapsed.total_seconds() < 3.0
                    if load_time_ok:
                        score += 3
                        details['fast_load'] = True
                        self.wins.append("✅ Website loads quickly")
                    else:
                        self.issues.append("⚠️ Website load time is slow")
                else:
                    self.issues.append(f"❌ Website returned status {resp.status_code}")
                    details['reachable'] = False
            except requests.exceptions.ConnectionError:
                self.issues.append("❌ Website is unreachable or domain not configured")
                details['reachable'] = False
            except requests.exceptions.Timeout:
                self.issues.append("❌ Website request timed out")
                details['reachable'] = False
            except Exception as e:
                self.issues.append(f"❌ Error checking website: {str(e)[:50]}")
                details['reachable'] = False
        else:
            self.issues.append("❌ No website URL provided — this is a major gap")
            details['reachable'] = False

        score = min(score, 20)
        self.scores['website_presence'] = score
        self.details['website_presence'] = details
        return score

    def check_google_business(self):
        score = 0
        details = {}
        name_lower = self.business_name.lower()

        gbp_indicators = [
            'pvt. ltd', 'private limited', 'company', 'store', 'shop',
            'restaurant', 'hotel', 'salon', 'clinic', 'center', 'centre',
            'enterprise', 'industries', 'inc', 'llc', 'corp', 'gmbh'
        ]

        has_gbp_indicator = any(ind in name_lower for ind in gbp_indicators)
        if has_gbp_indicator:
            score += 6
            details['likely_registered'] = True
            self.wins.append("✅ Business appears to be formally registered")
        else:
            self.issues.append("⚠️ Business may not be registered on Google Business Profile")

        if self.website_url:
            score += 4
            details['has_website_reference'] = True

        score += 3
        details['profile_possible'] = True

        score = min(score, 20)
        self.scores['google_business'] = score
        self.details['google_business'] = details
        return score

    def check_social_media(self):
        score = 0
        details = {}
        social_platforms = {
            'facebook': ['facebook.com', 'fb.com', 'facebook'],
            'instagram': ['instagram.com', 'insta'],
            'twitter': ['twitter.com', 'x.com'],
            'linkedin': ['linkedin.com'],
            'youtube': ['youtube.com', 'youtu.be'],
            'tiktok': ['tiktok.com']
        }

        found_platforms = []

        if self.website_url:
            try:
                url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
                resp = requests.get(url, timeout=8)
                html_lower = resp.text.lower()

                for platform, domains in social_platforms.items():
                    for domain in domains:
                        if domain in html_lower:
                            if platform not in found_platforms:
                                found_platforms.append(platform)
                            break
            except:
                pass

        name_lower = self.business_name.lower()
        for platform, keywords in social_platforms.items():
            for kw in keywords:
                if kw in name_lower:
                    if platform not in found_platforms:
                        found_platforms.append(platform)
                    break

        score += min(len(found_platforms) * 4, 12)
        details['platforms_found'] = found_platforms

        if found_platforms:
            self.wins.append(f"✅ Found on: {', '.join(found_platforms)}")
            if 'facebook' in found_platforms:
                score += 2
            if 'instagram' in found_platforms:
                score += 1
            details['social_presence'] = True
        else:
            self.issues.append("❌ No social media presence detected")
            details['social_presence'] = False

        if len(found_platforms) >= 3:
            self.wins.append("✅ Strong social media presence across multiple platforms")

        score = min(score, 15)
        self.scores['social_media'] = score
        self.details['social_media'] = details
        return score

    def check_mobile_friendly(self):
        score = 0
        details = {}

        if self.website_url:
            url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
            try:
                resp = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36'
                })
                html = resp.text.lower()

                viewport = '<meta name="viewport"' in html
                if viewport:
                    score += 6
                    details['viewport_meta'] = True
                    self.wins.append("✅ Mobile viewport meta tag found")

                media_queries = '@media' in html
                if media_queries:
                    score += 4
                    details['media_queries'] = True

                has_large_fonts = False
                for size in ['font-size: 16px', 'font-size:1rem', 'font-size: 1rem', 'font-size:16px']:
                    if size in html:
                        has_large_fonts = True
                        break
                if has_large_fonts:
                    score += 3
                    details['readable_fonts'] = True

                touch_targets = True
                score += 2
                details['touch_targets'] = True

                if not viewport:
                    self.issues.append("⚠️ Website not optimized for mobile (no viewport meta)")
                if not media_queries:
                    self.issues.append("⚠️ Website may not be responsive on mobile devices")
            except:
                self.issues.append("⚠️ Could not check mobile friendliness")
                score = 5
                details['error'] = True
        else:
            self.issues.append("❌ No website to check for mobile friendliness")
            details['no_website'] = True

        score = min(score, 15)
        self.scores['mobile_friendly'] = score
        self.details['mobile_friendly'] = details
        return score

    def check_online_reviews(self):
        score = 0
        details = {}
        name_lower = self.business_name.lower()

        review_indicators = {
            'rating': 0, 'star': 0, 'review': 0, 'testimonial': 0,
            'google review': 0, 'trustpilot': 0
        }

        if self.website_url:
            try:
                url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
                resp = requests.get(url, timeout=8)
                html_lower = resp.text.lower()
                for word in review_indicators:
                    if word in html_lower:
                        review_indicators[word] = html_lower.count(word)
            except:
                pass

        has_review_section = sum(review_indicators.values()) > 3
        if has_review_section:
            score += 5
            details['has_reviews_on_website'] = True
            self.wins.append("✅ Business displays reviews/testimonials")
        else:
            self.issues.append("⚠️ No reviews or testimonials found on website")

        score += 5
        details['review_platforms_possible'] = True

        score = min(score, 10)
        self.scores['online_reviews'] = score
        self.details['online_reviews'] = details
        return score

    def check_seo_basics(self):
        score = 0
        details = {}

        if self.website_url:
            url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
            try:
                resp = requests.get(url, timeout=10)
                html_lower = resp.text.lower()

                title_tag = re.search(r'<title>(.*?)</title>', html_lower, re.IGNORECASE)
                if title_tag and title_tag.group(1).strip():
                    score += 3
                    title = title_tag.group(1).strip()
                    details['title'] = title
                    if 30 <= len(title) <= 60:
                        score += 1
                        details['title_length_optimal'] = True
                    self.wins.append(f"✅ Page title found: \"{title[:40]}...\"")
                else:
                    self.issues.append("⚠️ Missing page title tag (critical for SEO)")

                meta_desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html_lower, re.IGNORECASE)
                if meta_desc and meta_desc.group(1).strip():
                    score += 2
                    details['meta_description'] = meta_desc.group(1).strip()[:50]
                else:
                    self.issues.append("⚠️ Missing meta description tag")

                has_h1 = bool(re.search(r'<h1[^>]*>', html_lower))
                if has_h1:
                    score += 2
                    details['has_h1'] = True
                else:
                    self.issues.append("⚠️ No H1 heading found")
            except:
                self.issues.append("⚠️ Could not check SEO basics")
                score = 2
                details['error'] = True
        else:
            self.issues.append("❌ Cannot check SEO — no website")

        score = min(score, 10)
        self.scores['seo_basics'] = score
        self.details['seo_basics'] = details
        return score

    def check_contact_accessibility(self):
        score = 0
        details = {}

        contact_patterns = {
            'phone': r'(?:\+[\d\s-]{1,4}[\s-]?)?\d{7,15}',
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
            score += 2
            self.wins.append("✅ WhatsApp contact available")
        else:
            self.issues.append("⚠️ WhatsApp contact not found — widely used globally")

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



