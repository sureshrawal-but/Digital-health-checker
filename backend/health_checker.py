import requests
import re
import json
import ssl
import socket
from urllib.parse import urlparse, urljoin
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


class DigitalHealthChecker:
    def __init__(self, business_name, website_url=None):
        self.business_name = business_name
        self.website_url = website_url
        self.scores = {}
        self.issues = []
        self.wins = []
        self.details = {}
        self.total_score = 0
        self.resp = None
        self.html = ""
        self.final_url = ""
        self.headers = {}

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

    def _fetch_website(self):
        url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
        try:
            self.resp = requests.get(url, timeout=15, allow_redirects=True, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            self.final_url = self.resp.url
            self.html = self.resp.text
            self.headers = dict(self.resp.headers)
        except Exception:
            self.resp = None
            self.html = ""
            self.final_url = url
            self.headers = {}

    def check_website_presence(self):
        score = 0
        details = {}

        if not self.website_url:
            self.issues.append("❌ No website URL provided — this is a major gap")
            details['reachable'] = False
            self.scores['website_presence'] = 0
            self.details['website_presence'] = details
            return 0

        details['url_checked'] = self.final_url

        if not self.resp or self.resp.status_code != 200:
            status = self.resp.status_code if self.resp else "unreachable"
            self.issues.append(f"❌ Website unreachable (status: {status})")
            details['reachable'] = False
            self.scores['website_presence'] = 0
            self.details['website_presence'] = details
            return 0

        score += 8
        details['reachable'] = True
        self.wins.append("✅ Website is live and accessible")

        if self.final_url.startswith('https://'):
            score += 4
            details['ssl'] = True
            self.wins.append("✅ SSL certificate present (HTTPS)")
            ssl_info = self._check_ssl_details()
            details['ssl_details'] = ssl_info
            if ssl_info.get('valid'):
                self.wins.append(f"✅ SSL valid until {ssl_info.get('expiry', 'unknown')}")
            else:
                self.issues.append("⚠️ SSL certificate issue: " + ssl_info.get('error', 'unknown'))
        else:
            self.issues.append("⚠️ Website not using HTTPS (security risk)")

        content_type = self.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            score += 2
            details['html'] = True

        load_time = self.resp.elapsed.total_seconds()
        details['load_time_seconds'] = round(load_time, 2)
        if load_time < 1.5:
            score += 3
            details['fast_load'] = True
            self.wins.append("✅ Website loads quickly")
        elif load_time < 3.0:
            score += 2
            details['acceptable_load'] = True
        else:
            self.issues.append(f"⚠️ Website load time is slow ({round(load_time, 1)}s)")

        security_headers = self._check_security_headers()
        details['security_headers'] = security_headers
        if security_headers.get('score', 0) >= 4:
            score += 1
            self.wins.append("✅ Good security headers")
        elif security_headers.get('score', 0) > 0:
            self.issues.append("⚠️ Some security headers missing")

        tech_stack = self._detect_technology()
        details['technology'] = tech_stack
        if tech_stack:
            self.wins.append(f"✅ Detected: {', '.join(tech_stack[:3])}")

        score = min(score, 20)
        self.scores['website_presence'] = score
        self.details['website_presence'] = details
        return score

    def _check_ssl_details(self):
        try:
            hostname = urlparse(self.final_url).netloc.split(':')[0]
            context = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    expiry = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                    days_left = (expiry - datetime.now()).days
                    return {
                        'valid': True,
                        'expiry': expiry.strftime('%Y-%m-%d'),
                        'days_left': days_left,
                        'issuer': dict(x[0] for x in cert.get('issuer', [])),
                        'subject': dict(x[0] for x in cert.get('subject', []))
                    }
        except Exception as e:
            return {'valid': False, 'error': str(e)}
        return {'valid': False, 'error': 'unknown'}

    def _check_security_headers(self):
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
        details['score'] = score
        return details

    def _detect_technology(self):
        tech = []
        html_lower = self.html.lower()
        headers = {k.lower(): v.lower() for k, v in self.headers.items()}

        if 'wp-content' in html_lower or 'wordpress' in html_lower:
            tech.append('WordPress')
        if 'shopify' in html_lower or 'shopify' in headers.get('server', ''):
            tech.append('Shopify')
        if 'wix' in html_lower or 'wix.com' in html_lower:
            tech.append('Wix')
        if 'squarespace' in html_lower:
            tech.append('Squarespace')
        if 'react' in html_lower or '__next' in html_lower:
            tech.append('React/Next.js')
        if 'vue' in html_lower and 'vue' not in ''.join(tech).lower():
            tech.append('Vue.js')
        if 'angular' in html_lower:
            tech.append('Angular')
        if 'cloudflare' in headers.get('server', '') or 'cf-ray' in headers:
            tech.append('Cloudflare')
        if 'nginx' in headers.get('server', ''):
            tech.append('Nginx')
        if 'apache' in headers.get('server', ''):
            tech.append('Apache')
        return tech

    def check_google_business(self):
        score = 0
        details = {}
        name_lower = self.business_name.lower()

        gbp_indicators = [
            'pvt. ltd', 'private limited', 'company', 'store', 'shop',
            'restaurant', 'hotel', 'salon', 'clinic', 'center', 'centre',
            'enterprise', 'industries', 'inc', 'llc', 'corp', 'gmbh',
            'ltd', 'limited', 'services', 'solutions', 'group', 'partners'
        ]

        has_gbp_indicator = any(ind in name_lower for ind in gbp_indicators)
        if has_gbp_indicator:
            score += 6
            details['likely_registered'] = True
            self.wins.append("✅ Business name suggests formal registration")
        else:
            self.issues.append("⚠️ Business name doesn't indicate formal registration — may lack Google Business Profile")

        if self.website_url and self.resp and self.resp.status_code == 200:
            score += 3
            details['has_website'] = True

        if 'map' in self.html.lower() or 'google.com/maps' in self.html.lower():
            score += 3
            details['map_embed'] = True
            self.wins.append("✅ Google Maps embed detected")

        score += 2
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
            'tiktok': ['tiktok.com'],
            'pinterest': ['pinterest.com'],
            'threads': ['threads.net']
        }

        found_platforms = []
        platform_urls = {}

        if self.website_url and self.resp and self.resp.status_code == 200:
            html_lower = self.html.lower()
            for platform, domains in social_platforms.items():
                for domain in domains:
                    if domain in html_lower:
                        if platform not in found_platforms:
                            found_platforms.append(platform)
                            break

        name_lower = self.business_name.lower()
        for platform, keywords in social_platforms.items():
            for kw in keywords:
                if kw in name_lower:
                    if platform not in found_platforms:
                        found_platforms.append(platform)
                    break

        score += min(len(found_platforms) * 3, 12)
        details['platforms_found'] = found_platforms
        details['platform_count'] = len(found_platforms)

        if found_platforms:
            self.wins.append(f"✅ Social presence: {', '.join(found_platforms)}")
            if 'facebook' in found_platforms:
                score += 1
            if 'instagram' in found_platforms:
                score += 1
            if 'linkedin' in found_platforms:
                score += 1
            details['social_presence'] = True
        else:
            self.issues.append("❌ No social media presence detected")
            details['social_presence'] = False

        if len(found_platforms) >= 4:
            score += 1
            self.wins.append("✅ Strong multi-platform social presence")

        score = min(score, 15)
        self.scores['social_media'] = score
        self.details['social_media'] = details
        return score

    def check_mobile_friendly(self):
        score = 0
        details = {}

        if not self.website_url or not self.resp or self.resp.status_code != 200:
            self.issues.append("❌ No website to check for mobile friendliness")
            details['no_website'] = True
            self.scores['mobile_friendly'] = 0
            self.details['mobile_friendly'] = details
            return 0

        html = self.html.lower()

        viewport = '<meta name="viewport"' in html
        if viewport:
            score += 5
            details['viewport_meta'] = True
            self.wins.append("✅ Mobile viewport meta tag found")
        else:
            self.issues.append("⚠️ Website not optimized for mobile (no viewport meta)")

        media_queries = '@media' in html
        if media_queries:
            score += 3
            details['media_queries'] = True
            self.wins.append("✅ CSS media queries detected")
        else:
            self.issues.append("⚠️ No media queries — may not be responsive")

        has_responsive_images = 'srcset' in html or 'picture' in html
        if has_responsive_images:
            score += 2
            details['responsive_images'] = True

        has_touch_friendly = any(x in html for x in ['touch-action', 'pointer-events', 'user-select'])
        if has_touch_friendly:
            score += 1
            details['touch_friendly'] = True

        no_horizontal_scroll = 'overflow-x: hidden' in html or 'max-width: 100%' in html
        if no_horizontal_scroll:
            score += 1
            details['no_horizontal_scroll'] = True

        mobile_ua_resp = None
        try:
            mobile_ua_resp = requests.get(self.final_url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15'
            })
            mobile_html = mobile_ua_resp.text.lower()
            if '<meta name="viewport"' in mobile_html:
                score += 1
                details['mobile_ua_viewport'] = True
        except:
            pass

        if not viewport:
            score = max(0, score - 2)

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
            'google review': 0, 'trustpilot': 0, 'yelp': 0, 'angie': 0,
            'tripadvisor': 0, 'facebook review': 0
        }

        review_platforms = []

        if self.website_url and self.resp and self.resp.status_code == 200:
            html_lower = self.html.lower()
            for word in review_indicators:
                if word in html_lower:
                    review_indicators[word] = html_lower.count(word)
                    if word in ['google review', 'trustpilot', 'yelp', 'angie', 'tripadvisor', 'facebook review']:
                        review_platforms.append(word.replace(' review', '').title())

        has_review_section = sum(review_indicators.values()) > 3
        if has_review_section:
            score += 4
            details['has_reviews_on_website'] = True
            self.wins.append("✅ Business displays reviews/testimonials on website")
        else:
            self.issues.append("⚠️ No reviews or testimonials found on website")

        if review_platforms:
            score += 2
            details['platforms_mentioned'] = review_platforms
            self.wins.append(f"✅ Review platforms referenced: {', '.join(review_platforms)}")

        score += 2
        details['review_platforms_possible'] = True

        score = min(score, 10)
        self.scores['online_reviews'] = score
        self.details['online_reviews'] = details
        return score

    def check_seo_basics(self):
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
            details['title'] = title
            if 30 <= len(title) <= 60:
                score += 1
                details['title_length_optimal'] = True
                self.wins.append(f"✅ Optimal title length: {len(title)} chars")
            elif len(title) > 60:
                self.issues.append(f"⚠️ Title too long ({len(title)} chars) — may truncate in search")
            else:
                self.issues.append(f"⚠️ Title too short ({len(title)} chars) — add keywords")
            self.wins.append(f"✅ Page title found: \"{title[:50]}...\"")
        else:
            self.issues.append("⚠️ Missing page title tag (critical for SEO)")

        meta_desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html_lower, re.IGNORECASE)
        if meta_desc and meta_desc.group(1).strip():
            desc = meta_desc.group(1).strip()
            score += 2
            details['meta_description'] = desc[:100]
            if 120 <= len(desc) <= 160:
                score += 1
                details['meta_desc_optimal'] = True
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
            self.wins.append("✅ Open Graph tags present")
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

        robots_txt = self._check_robots_txt()
        details['robots_txt'] = robots_txt
        if robots_txt:
            score += 1
            self.wins.append("✅ robots.txt found")

        sitemap = self._check_sitemap()
        details['sitemap'] = sitemap
        if sitemap:
            score += 1
            self.wins.append("✅ XML sitemap found")

        structured_data = 'application/ld+json' in html_lower or 'schema.org' in html_lower
        details['structured_data'] = structured_data
        if structured_data:
            score += 1
            self.wins.append("✅ Structured data (Schema.org) detected")

        score = min(score, 10)
        self.scores['seo_basics'] = score
        self.details['seo_basics'] = details
        return score

    def _check_robots_txt(self):
        try:
            base = f"{urlparse(self.final_url).scheme}://{urlparse(self.final_url).netloc}"
            r = requests.get(urljoin(base, '/robots.txt'), timeout=5)
            return r.status_code == 200 and len(r.text) > 0
        except:
            return False

    def _check_sitemap(self):
        try:
            base = f"{urlparse(self.final_url).scheme}://{urlparse(self.final_url).netloc}"
            for path in ['/sitemap.xml', '/sitemap_index.xml', '/sitemap/sitemap.xml']:
                r = requests.get(urljoin(base, path), timeout=5)
                if r.status_code == 200 and 'xml' in r.headers.get('Content-Type', ''):
                    return True
        except:
            return False
        return False

    def check_contact_accessibility(self):
        score = 0
        details = {}

        contact_patterns = {
            'phone': r'(?:\+[\d\s-]{1,4}[\s-]?)?\d{7,15}',
            'email': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            'address': r'(?:street|road|avenue|drive|boulevard|ln|drive|square|plaza|building|suite|floor|office|unit|city|state|zip|postcode)',
            'whatsapp': r'(?:whatsapp|wa\.me|wa.me)',
            'contact_form': r'<form[^>]*>|contact[_-]?form',
            'live_chat': r'(?:livechat|tawk|intercom|crisp|zendesk|chat\.widget)',
            'telegram': r'(?:telegram|t\.me|t.me)',
            'skype': r'(?:skype|callto:|skype:)',
        }

        found_contacts = {}

        if self.website_url and self.resp and self.resp.status_code == 200:
            html_lower = self.html.lower()
            for contact_type, pattern in contact_patterns.items():
                matches = re.findall(pattern, html_lower, re.IGNORECASE)
                if matches:
                    found_contacts[contact_type] = matches[:3]

        phone_found = 'phone' in found_contacts
        email_found = 'email' in found_contacts
        address_found = 'address' in found_contacts
        whatsapp_found = 'whatsapp' in found_contacts
        form_found = 'contact_form' in found_contacts
        chat_found = 'live_chat' in found_contacts

        if phone_found:
            score += 2
            self.wins.append("✅ Phone number found")
        else:
            self.issues.append("⚠️ No phone number listed")

        if email_found:
            score += 2
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
            self.issues.append("⚠️ WhatsApp contact not found")

        if form_found:
            score += 1
            self.wins.append("✅ Contact form detected")
        else:
            self.issues.append("⚠️ No contact form found")

        if chat_found:
            score += 1
            self.wins.append("✅ Live chat widget detected")

        details['found'] = found_contacts
        details['contact_methods_count'] = len(found_contacts)

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


def generate_demo_report(business_name, website_url=None, location="Global"):
    """
    Generate a simulated digital health report WITHOUT making HTTP requests.
    Uses text analysis of inputs to estimate scores.
    """
    text_lower = (business_name + ' ' + (website_url or '') + ' ' + location).lower()
    scores = {}
    issues = []
    wins = []

    ws = 0
    if website_url:
        ws += 8
        wins.append("✅ Website URL provided")
        if website_url.startswith('https://') or '.com' in website_url:
            ws += 4
        if len(website_url) > 10:
            ws += 3
        if '.' in website_url:
            ws += 3
    else:
        issues.append("❌ No website URL — critical gap for credibility")
    scores["website_presence"] = {"score": min(ws, 20), "max": 20, "label": "Website Presence", "icon": "🌐"}

    gb = 5
    formal_indicators = ['pvt', 'ltd', 'private', 'limited', 'company', 'store', 'restaurant', 'hotel', 'salon', 'center', 'enterprise']
    if any(w in text_lower for w in formal_indicators):
        gb += 5
        wins.append("✅ Formal business name detected")
    if location and location.lower() != 'global':
        gb += 5
    if website_url:
        gb += 3
    if '.' in business_name:
        gb += 2
    if gb < 10:
        issues.append("⚠️ May not have Google Business Profile — essential for local search")
    scores["google_business"] = {"score": min(gb, 20), "max": 20, "label": "Google Business Profile", "icon": "📍"}

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

    mf = 0
    if website_url:
        mf += 6 + 4
        if '.com' in website_url:
            mf += 3
        mf += 2
    else:
        issues.append("⚠️ Cannot assess mobile friendliness — no website")
        mf = 4
    scores["mobile_friendly"] = {"score": min(mf, 15), "max": 15, "label": "Mobile Friendliness", "icon": "📲"}

    rv = 3
    review_keywords = ['rating', 'review', 'star', 'testimonials', 'google review']
    if any(w in text_lower for w in review_keywords):
        rv += 4
        wins.append("✅ Reviews/testimonials found")
    if location and location.lower() != 'global':
        rv += 2
    if rv < 5:
        issues.append("⚠️ No reviews detected — social proof is crucial")
    scores["online_reviews"] = {"score": min(rv, 10), "max": 10, "label": "Online Reviews", "icon": "⭐"}

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
        summary = f"✨ {business_name} has a strong digital foundation! With a working website and social media presence, you're ahead of most businesses. Focus on collecting reviews and optimizing your Google Business Profile to reach even more customers."
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
        report["recommendations"].append({"priority": "Critical", "action": "Create a website (use free tools like Google Sites, Wix, or WordPress)", "impact": "Opens your business to 24/7 global discovery", "cost": "Free – $20/month"})
    if not platforms_found:
        report["recommendations"].append({"priority": "High", "action": "Create Facebook and Instagram business pages", "impact": "Reach 80%+ of online population", "cost": "Free"})

    report["recommendations"].append({"priority": "High", "action": "Claim and optimize your Google Business Profile", "impact": "Show up in Google Maps and local search results", "cost": "Free"})
    report["recommendations"].append({"priority": "Medium", "action": "Add WhatsApp contact — the most popular messaging app globally", "impact": "Makes it easy for customers to reach you directly", "cost": "Free"})
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