import requests
import re
import json
import os
import time
from urllib.parse import urlparse, urljoin
from typing import Optional, List, Dict, Any

PILLAR_CONFIG = {
    "website_presence": {"max": 20, "weight": 0.20, "label": "Website Presence"},
    "google_business": {"max": 20, "weight": 0.20, "label": "Google Business Profile"},
    "social_media": {"max": 15, "weight": 0.15, "label": "Social Media Presence"},
    "mobile_friendly": {"max": 15, "weight": 0.15, "label": "Mobile Friendliness"},
    "online_reviews": {"max": 10, "weight": 0.10, "label": "Online Reviews"},
    "seo_basics": {"max": 10, "weight": 0.10, "label": "SEO Basics"},
    "contact_accessibility": {"max": 10, "weight": 0.10, "label": "Contact Accessibility"},
}

class DigitalHealthChecker:
    def __init__(self, business_name: str, website_url: Optional[str] = None):
        self.business_name = business_name.strip()
        self.website_url = website_url.strip() if website_url else None
        self.base_url = None
        self.normalized_name = re.sub(r'[^\w\s]', '', self.business_name.lower()).strip()
        self.scores = {}
        self.details = {}
        self.issues = []
        self.wins = []
        self.resp = None
        self.html = ""
        self.final_url = ""
        self.headers = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def _fetch(self, url, timeout=10):
        try:
            return self.session.get(url, timeout=timeout, allow_redirects=True)
        except:
            return None

    def _fetch_website(self):
        url = self.website_url if self.website_url.startswith(('http://', 'https://')) else f'https://{self.website_url}'
        try:
            self.resp = self.session.get(url, timeout=12, allow_redirects=True)
            self.final_url = self.resp.url
            self.html = self.resp.text
            self.headers = dict(self.resp.headers)
            parsed = urlparse(self.final_url)
            self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        except requests.exceptions.Timeout:
            self.issues.append("Website request timed out (>12s)")
        except requests.exceptions.ConnectionError:
            self.issues.append("Could not connect to website")
        except Exception as e:
            self.issues.append(f"Fetch error: {str(e)[:100]}")

    def _get_url(self, path):
        return urljoin(self.base_url or f"https://{self.website_url}", path) if self.base_url or self.website_url else None

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
        score = 6
        self.wins.append("Website is live and accessible")
        checks = {}
        if self.resp.url.startswith('https://'):
            score += 3
            checks["https"] = True
            self.wins.append("HTTPS enabled - secure connection")
        else:
            self.issues.append("Website not using HTTPS")
            checks["https"] = False
        load_time = self.resp.elapsed.total_seconds()
        checks["load_time"] = round(load_time, 2)
        if load_time < 1.5:
            score += 2
            self.wins.append(f"Fast load time ({load_time:.1f}s)")
        elif load_time >= 3:
            self.issues.append(f"Slow load time ({load_time:.1f}s) - aim for <2s")
        content_type = self.resp.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            score += 1
        word_count = len(re.findall(r'\b\w+\b', self.html))
        checks["word_count"] = word_count
        if word_count > 200:
            score += 1
            self.wins.append("Substantial content on page")
        else:
            self.issues.append("Very thin content - add more text")
        if re.search(r'<link[^>]*rel=["\']icon["\']', self.html, re.IGNORECASE):
            score += 1
            self.wins.append("Favicon detected")
        else:
            self.issues.append("No favicon found")
        if re.search(r'copyright|©|\d{4}', self.html, re.IGNORECASE):
            score += 1
            self.wins.append("Copyright notice present (establishes legitimacy)")
        else:
            self.issues.append("No copyright notice found")
        robots_url = self._get_url("/robots.txt")
        if robots_url:
            robots_resp = self._fetch(robots_url, timeout=5)
            if robots_resp and robots_resp.status_code == 200:
                score += 1
                self.wins.append("robots.txt found")
        sitemap_url = self._get_url("/sitemap.xml")
        if sitemap_url:
            sm_resp = self._fetch(sitemap_url, timeout=5)
            if sm_resp and sm_resp.status_code == 200:
                score += 1
                self.wins.append("XML sitemap found")
        security_score = 0
        sh = ['X-Content-Type-Options', 'X-Frame-Options', 'Strict-Transport-Security', 'Content-Security-Policy']
        header_map = {k.lower(): v for k, v in self.headers.items()}
        for h in sh:
            if h.lower() in header_map:
                security_score += 1
        if security_score >= 3:
            score += 2
            self.wins.append("Good security headers")
        elif security_score >= 1:
            score += 1
        else:
            self.issues.append("Missing security headers (X-Content-Type-Options, X-Frame-Options, HSTS)")
        if re.search(r'<meta[^>]*http-equiv=["\']refresh["\']', self.html, re.IGNORECASE):
            self.issues.append("Page uses meta refresh - bad for UX and SEO")
        checks["security_headers"] = security_score
        checks["favicon"] = bool(re.search(r'icon', self.html.lower()))
        self.scores["website_presence"] = min(score, 20)
        self.details["website_presence"] = checks

    def _check_google_business(self):
        score = 4
        checks = {}
        gbp_indicators = ['pvt', 'ltd', 'private', 'limited', 'company', 'store', 'shop',
                          'restaurant', 'hotel', 'salon', 'clinic', 'center', 'centre',
                          'enterprise', 'industries', 'inc', 'llc', 'corp', 'gmbh', 'services', 'group']
        if any(ind in self.normalized_name for ind in gbp_indicators):
            score += 3
            self.wins.append("Business name suggests formal registration")
        else:
            self.issues.append("Business name may not be formally registered")
        if self.website_url:
            score += 2
            self.wins.append("Website available for GBP verification")
        schema_types = re.findall(r'"@type"\s*:\s*"(\w+)"', self.html)
        checks["schema_types"] = list(set(schema_types))
        has_local_biz = 'LocalBusiness' in self.html or 'localbusiness' in self.html.lower()
        has_organization = 'Organization' in self.html
        if has_local_biz or has_organization:
            score += 4
            self.wins.append("LocalBusiness/Organization schema detected (helps Google understand your business)")
        if re.search(r'"openingHours[\w"]*\s*":', self.html):
            score += 2
            self.wins.append("Opening hours specified in schema")
        if re.search(r'"telephone"\s*:', self.html):
            score += 2
            self.wins.append("Phone number in schema markup")
        if re.search(r'"address"\s*:', self.html):
            score += 2
            self.wins.append("Address in schema markup")
        if re.search(r'"aggregateRating"\s*:', self.html):
            score += 1
            self.wins.append("Aggregate rating in schema (boosts local SEO)")
        if 'maps.google.com' in self.html.lower() or 'google.com/maps' in self.html.lower():
            score += 2
            self.wins.append("Google Maps embed found")
        if not has_local_biz and not has_organization:
            self.issues.append("No LocalBusiness/Organization schema - critical for local SEO")
        if score < 8:
            self.issues.append("Google Business Profile may be missing or unclaimed")
        self.scores["google_business"] = min(score, 20)
        self.details["google_business"] = checks

    def _check_social_media(self):
        platforms = {
            'facebook': ['facebook.com/', 'fb.com/', 'facebook.com\/'],
            'instagram': ['instagram.com/'],
            'twitter': ['twitter.com/', 'x.com/'],
            'linkedin': ['linkedin.com/company/', 'linkedin.com/in/'],
            'youtube': ['youtube.com/@', 'youtube.com/channel/', 'youtu.be/'],
            'tiktok': ['tiktok.com/@'],
            'pinterest': ['pinterest.com/'],
            'telegram': ['t.me/', 'telegram.me/'],
            'whatsapp': ['wa.me/', 'whatsapp.com/'],
        }
        social_links = {p: [] for p in platforms}
        if self.html:
            # Find all href links
            links = re.findall(r'href=["\'](https?://[^"\']+)["\']', self.html, re.IGNORECASE)
            links += re.findall(r'href=["\'](//[^"\']+)["\']', self.html, re.IGNORECASE)
            for link in links:
                link_lower = link.lower()
                for platform, patterns in platforms.items():
                    for pattern in patterns:
                        if pattern in link_lower:
                            social_links[platform].append(link)
                            break
            # Check for embeds
            if 'instagram.com/p/' in self.html.lower() or 'instagram.com/reel/' in self.html.lower():
                if 'instagram' not in social_links or not social_links['instagram']:
                    social_links['instagram'].append("(embed detected)")
            if 'twitter.com' in self.html.lower() or 'platform.twitter.com' in self.html.lower():
                if 'twitter' not in social_links or not social_links['twitter']:
                    social_links['twitter'].append("(embed detected)")
            if 'youtube.com/embed/' in self.html.lower():
                if 'youtube' not in social_links or not social_links['youtube']:
                    social_links['youtube'].append("(embed detected)")
            if 'facebook.com/plugins/' in self.html.lower():
                if 'facebook' not in social_links or not social_links['facebook']:
                    social_links['facebook'].append("(page plugin detected)")
        found_platforms = {p: links for p, links in social_links.items() if links}
        platform_count = len(found_platforms)
        score = min(platform_count * 3, 12)
        if platform_count == 0:
            self.issues.append("No social media links found on website")
            score = 2
        elif platform_count <= 2:
            self.issues.append(f"Only {platform_count} social platform(s) linked - add more for better reach")
        elif platform_count >= 4:
            self.wins.append(f"Strong multi-platform social presence ({platform_count} platforms)")
        else:
            self.wins.append(f"{platform_count} social platforms linked")
        # Check for social sharing buttons
        share_patterns = ['share this', 'social share', 'share button', 'addthis', 'sharethis']
        if any(p in self.html.lower() for p in share_patterns):
            score += 2
            self.wins.append("Social sharing buttons/widgets detected")
        if 'whatsapp' in self.html.lower() or 'wa.me' in self.html.lower():
            score += 1
            self.wins.append("WhatsApp contact available")
        self.scores["social_media"] = min(score, 15)
        self.details["social_media"] = {"platforms_found": list(found_platforms.keys()), "platform_count": platform_count}

    def _check_mobile_friendly(self):
        score = 0
        if not self.website_url or not self.resp or self.resp.status_code != 200:
            self.issues.append("No website to check for mobile friendliness")
            self.scores["mobile_friendly"] = 0
            self.details["mobile_friendly"] = {}
            return
        html = self.html.lower()
        checks = {}
        # Viewport meta
        viewport_match = re.search(r'<meta\s+name=["\']viewport["\']\s+content=["\']([^"\']+)["\']', self.html, re.IGNORECASE)
        if viewport_match:
            content = viewport_match.group(1).lower()
            checks["viewport"] = content
            if 'width=device-width' in content and 'initial-scale=1' in content:
                score += 5
                self.wins.append("Viewport meta properly configured")
            elif 'width=device-width' in content:
                score += 3
                self.issues.append("Viewport meta missing initial-scale=1")
            else:
                score += 2
                self.issues.append("Viewport meta present but not optimally configured")
        else:
            self.issues.append("No viewport meta tag - site not optimized for mobile")
        # Media queries
        if '@media' in html:
            score += 3
            self.wins.append("CSS media queries detected (responsive design)")
        else:
            self.issues.append("No CSS media queries - site may not be responsive")
        # Responsive images
        if 'srcset' in html or '<picture' in html:
            score += 2
            checks["responsive_images"] = True
        # Touch icons
        apple_icon = re.search(r'<link[^>]*rel=["\']apple-touch-icon["\']', self.html, re.IGNORECASE)
        if apple_icon:
            score += 1
            self.wins.append("Apple touch icon found")
        # Theme color
        if 'theme-color' in html or 'theme_color' in html:
            score += 1
            checks["theme_color"] = True
        # Touch events
        touch_events = any(x in html for x in ['touch-action', 'pointer-events'])
        if touch_events:
            score += 1
        # Font size legibility
        font_sizes = re.findall(r'font-size\s*:\s*(\d+)px', html)
        small_fonts = [int(s) for s in font_sizes if int(s) < 12]
        if small_fonts:
            self.issues.append(f"Font sizes as small as {min(small_fonts)}px - may be hard to read on mobile")
        else:
            score += 1
        # Test with mobile UA
        try:
            mobile_resp = self.session.get(self.final_url or self.website_url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15'
            })
            mobile_html = mobile_resp.text.lower()
            if '<meta name="viewport"' in mobile_html:
                score += 1
            # Check if mobile version is different
            if len(mobile_html) != len(self.html) * 0.9:  # significantly different
                checks["separate_mobile_version"] = True
        except:
            pass
        self.scores["mobile_friendly"] = min(score, 15)
        self.details["mobile_friendly"] = checks

    def _check_online_reviews(self):
        score = 2
        checks = {}
        review_signals = {
            'aggregateRating': r'"aggregateRating"\s*:',
            'review_count': r'"reviewCount"\s*:',
            'rating_value': r'"ratingValue"\s*:',
            'best_rating': r'"bestRating"\s*:',
        }
        found_schema = []
        for name, pattern in review_signals.items():
            if re.search(pattern, self.html):
                found_schema.append(name)
        if found_schema:
            score += 4
            self.wins.append(f"Review schema detected ({', '.join(found_schema)})")
            checks["review_schema"] = found_schema
        # Extract rating value if present
        rating_match = re.search(r'"ratingValue"\s*:\s*"*([\d.]+)"*', self.html)
        if rating_match:
            checks["rating"] = float(rating_match.group(1))
        review_count_match = re.search(r'"reviewCount"\s*:\s*(\d+)', self.html)
        if review_count_match:
            checks["review_count"] = int(review_count_match.group(1))
            if int(review_count_match.group(1)) > 10:
                self.wins.append(f"{review_count_match.group(1)} reviews structured in schema")
        # Check for review platform badges/links
        review_platforms = ['trustpilot', 'yelp', 'tripadvisor', 'google.*review', 'g2.com', 'capterra']
        found_platforms = []
        for p in review_platforms:
            if re.search(p, self.html.lower()):
                found_platforms.append(p.split('.*')[0] if '.*' in p else p)
        if found_platforms:
            score += 2
            checks["review_platforms"] = found_platforms
            self.wins.append(f"Review platform links found: {', '.join(found_platforms)}")
        # Check for testimonial sections
        testimonial_keywords = ['testimonial', 'what our customers say', 'client feedback', 'success stories']
        if any(kw in self.html.lower() for kw in testimonial_keywords):
            score += 2
            self.wins.append("Testimonials section found on website")
            checks["testimonials"] = True
        if not found_schema and not found_platforms:
            if not re.search(r'review|rating|star|testimonial', self.html.lower()):
                self.issues.append("No reviews, ratings, or testimonials found anywhere")
            else:
                score += 1
                self.issues.append("Review mentions found but no structured review schema")
        self.scores["online_reviews"] = min(score, 10)
        self.details["online_reviews"] = checks

    def _check_seo_basics(self):
        score = 0
        if not self.website_url or not self.resp or self.resp.status_code != 200:
            self.issues.append("Cannot check SEO - no website")
            self.scores["seo_basics"] = 0
            self.details["seo_basics"] = {}
            return
        html_lower = self.html.lower()
        checks = {}
        # Title tag
        title_tag = re.search(r'<title>(.*?)</title>', self.html, re.IGNORECASE | re.DOTALL)
        if title_tag and title_tag.group(1).strip():
            title_text = title_tag.group(1).strip()
            title_len = len(title_text)
            score += 2
            checks["title"] = title_text[:80]
            if 30 <= title_len <= 60:
                score += 1
                self.wins.append(f"Title tag optimal length ({title_len} chars)")
            else:
                self.issues.append(f"Title too {'short' if title_len < 30 else 'long'} ({title_len} chars, ideal: 30-60)")
        else:
            self.issues.append("Missing page title tag (critical for SEO)")
        # Meta description
        meta_desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', self.html, re.IGNORECASE)
        if meta_desc and meta_desc.group(1).strip():
            desc_text = meta_desc.group(1).strip()
            desc_len = len(desc_text)
            score += 1
            checks["description"] = desc_text[:100]
            if 120 <= desc_len <= 160:
                score += 1
                self.wins.append(f"Meta description optimal length ({desc_len} chars)")
            else:
                self.issues.append(f"Meta description {'too short' if desc_len < 120 else 'too long'} ({desc_len} chars)")
        else:
            self.issues.append("Missing meta description tag")
        # Heading structure
        h1_tags = re.findall(r'<h1[^>]*>', self.html, re.IGNORECASE)
        h2_tags = re.findall(r'<h2[^>]*>', self.html, re.IGNORECASE)
        h3_tags = re.findall(r'<h3[^>]*>', self.html, re.IGNORECASE)
        checks["heading_structure"] = {"h1": len(h1_tags), "h2": len(h2_tags), "h3": len(h3_tags)}
        if len(h1_tags) == 1:
            score += 1
            self.wins.append("Proper heading structure (single H1)")
        elif len(h1_tags) == 0:
            self.issues.append("No H1 heading found - critical for SEO")
        else:
            self.issues.append(f"Multiple H1 tags ({len(h1_tags)}) - use only one per page")
        if len(h2_tags) > 0:
            score += 1
        if len(h3_tags) > 0:
            score += 0.5
        # Image alt attributes
        images = re.findall(r'<img[^>]*>', self.html, re.IGNORECASE)
        total_imgs = len(images)
        imgs_with_alt = sum(1 for img in images if re.search(r'alt=["\']', img, re.IGNORECASE))
        imgs_without_alt = total_imgs - imgs_with_alt
        checks["images"] = {"total": total_imgs, "with_alt": imgs_with_alt}
        if total_imgs > 0:
            alt_pct = (imgs_with_alt / total_imgs) * 100
            if alt_pct >= 80:
                score += 1
                self.wins.append(f"Good alt text usage ({imgs_with_alt}/{total_imgs} images)")
            elif alt_pct > 0:
                self.issues.append(f"{imgs_without_alt}/{total_imgs} images missing alt text")
            else:
                self.issues.append(f"All {total_imgs} images missing alt text")
        # Open Graph tags
        og_tags = {}
        for og in ['og:title', 'og:description', 'og:image', 'og:url', 'og:type']:
            if og in html_lower:
                og_tags[og] = True
        checks["open_graph"] = list(og_tags.keys())
        if len(og_tags) >= 4:
            score += 1
            self.wins.append("Rich Open Graph tags detected (improves social sharing)")
        elif len(og_tags) >= 2:
            score += 0.5
        # Twitter cards
        if any(k in html_lower for k in ['twitter:card', 'twitter:title', 'twitter:description']):
            score += 0.5
            checks["twitter_cards"] = True
        # Canonical URL
        canonical = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\'](.*?)["\']', self.html, re.IGNORECASE)
        if canonical:
            score += 0.5
            checks["canonical"] = canonical.group(1)
        # Language attribute
        lang_match = re.search(r'<html[^>]*\blang=["\'](\w+)["\']', self.html, re.IGNORECASE)
        if lang_match:
            score += 0.5
            checks["language"] = lang_match.group(1)
        else:
            self.issues.append("No language attribute on <html> tag")
        # Robots meta
        if re.search(r'<meta\s+name=["\']robots["\']', self.html, re.IGNORECASE):
            score += 0.5
            checks["robots_meta"] = True
        # Internal links
        internal_links = len(re.findall(r'href=["\']/', self.html))
        checks["internal_links"] = internal_links
        if internal_links > 5:
            score += 0.5
        self.scores["seo_basics"] = min(int(round(score)), 10)
        self.details["seo_basics"] = checks

    def _check_contact_accessibility(self):
        score = 0
        checks = {}
        phone_patterns = [
            r'(?:\+977[\s-]?)?9[78]\d{8}',
            r'(?:\+91[\s-]?)?[6-9]\d{9}',
            r'(?:\+1[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}',
            r'(?:\+44[\s-]?)?\d{4}[\s-]?\d{6}',
            r'[\+\d][\d\s\-\(\)]{7,15}',
        ]
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        found = {}
        html_to_search = self.html
        if html_to_search:
            for i, pat in enumerate(phone_patterns):
                matches = re.findall(pat, html_to_search)
                if matches:
                    # Filter out false positives (numbers that look like years or CSS values)
                    clean = [m for m in matches if len(re.sub(r'[\s\-\(\)]', '', m)) >= 7]
                    if clean:
                        found['phone'] = clean[0]
                        break
            email_matches = re.findall(email_pattern, html_to_search)
            if email_matches:
                # Filter obvious non-contact emails
                clean_emails = [e for e in email_matches if not e.startswith('example') and not e.endswith('.png') and not e.endswith('.jpg') and not e.endswith('.css') and not e.endswith('.js')]
                if clean_emails:
                    found['email'] = clean_emails[0]
            # Check for contact form
            form_keywords = ['contact us', 'get in touch', 'send us a message', 'contact form']
            if any(kw in html_to_search.lower() for kw in form_keywords):
                score += 2
                self.wins.append("Contact form available")
                checks["contact_form"] = True
            # Check for live chat
            chat_keywords = ['live chat', 'chat now', 'start chat', 'intercom', 'tawk.to', 'livechat', 'crisp', 'zendesk']
            if any(kw in html_to_search.lower() for kw in chat_keywords):
                score += 2
                self.wins.append("Live chat support detected")
                checks["live_chat"] = True
            # Google Maps embed
            if 'google.com/maps' in html_to_search.lower() or 'maps/embed' in html_to_search.lower():
                score += 1
                self.wins.append("Google Maps embed showing business location")
                checks["maps_embed"] = True
            # Contact page link
            contact_links = re.findall(r'href=["\']([^"\']*(?:contact|get-in-touch|reach-us|about)[^"\']*)["\']', html_to_search, re.IGNORECASE)
            if contact_links:
                score += 1
                self.wins.append("Dedicated contact page linked")
                checks["contact_page"] = contact_links[0]
            # WhatsApp
            if 'wa.me' in html_to_search.lower() or 'whatsapp.com' in html_to_search.lower() or 'whatsapp' in html_to_search.lower():
                found['whatsapp'] = True
                score += 1
                self.wins.append("WhatsApp contact available")
            # Address patterns
            addr_keywords = ['street', 'road', 'avenue', 'drive', 'boulevard', 'square', 'plaza',
                             'building', 'suite', 'floor', 'office', 'unit', 'ltd', 'pvt', 'p.']
            if any(kw in html_to_search.lower() for kw in addr_keywords):
                found['address'] = True
                score += 1
                self.wins.append("Physical address mentioned")
        if 'phone' in found:
            score += 2
            self.wins.append(f"Phone number found")
            checks["phone"] = found['phone']
        else:
            self.issues.append("No phone number found - critical for customer trust")
        if 'email' in found:
            score += 1
            self.wins.append(f"Email address found")
            checks["email"] = found['email']
        else:
            self.issues.append("No email address found")
        if not checks.get("contact_form") and not checks.get("live_chat"):
            if 'phone' not in found and 'email' not in found:
                self.issues.append("No contact method found (phone, email, or form)")
        self.scores["contact_accessibility"] = min(score, 10)
        self.details["contact_accessibility"] = checks

    def get_health_status(self, total_score):
        if total_score >= 80:
            return {"status": "Digitally Healthy", "color": "green", "emoji": "\U0001f7e2", "type": "excellent"}
        elif total_score >= 60:
            return {"status": "Needs Improvement", "color": "yellow", "emoji": "\U0001f7e1", "type": "fair"}
        elif total_score >= 40:
            return {"status": "Seriously Behind", "color": "orange", "emoji": "\U0001f7e0", "type": "poor"}
        else:
            return {"status": "Digitally Invisible", "color": "red", "emoji": "\U0001f534", "type": "critical"}

    def get_category_scores(self):
        result = {}
        for key, cfg in PILLAR_CONFIG.items():
            result[key] = {"score": self.scores.get(key, 0), "max": cfg["max"], "label": cfg["label"]}
        return result

    def run_all_checks(self) -> Dict[str, Any]:
        try:
            if self.website_url:
                self._fetch_website()
            self._check_website_presence()
            self._check_google_business()
            self._check_social_media()
            self._check_mobile_friendly()
            self._check_online_reviews()
            self._check_seo_basics()
            self._check_contact_accessibility()
        except Exception as e:
            for k in PILLAR_CONFIG:
                if k not in self.scores:
                    self.scores[k] = 0
                if k not in self.details:
                    self.details[k] = {}
            self.issues.append(f"Analysis error: {str(e)}")
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
        ws += 6
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
        seo += 6
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
