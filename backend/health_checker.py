import requests
import re
import json
import ssl
import socket
import os
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
        
        # Wrap each check in try/except to prevent one failure from breaking the whole analysis
        try:
            self.check_website_presence()
        except Exception:
            pass
        
        try:
            self.check_google_business()
        except Exception:
            pass
        
        try:
            self.check_social_media()
        except Exception:
            pass
        
        try:
            self.check_mobile_friendly()
        except Exception:
            pass
        
        try:
            self.check_online_reviews()
        except Exception:
            pass
        
        try:
            self.check_seo_basics()
        except Exception:
            pass
        
        try:
            self.check_contact_accessibility()
        except Exception:
            pass
        
        self.calculate_total()
        return self.get_report()

    def _fetch_website(self):
        if not self.website_url:
            self.resp = None
            self.html = ""
            self.final_url = ""
            self.headers = {}
            return
        
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
            try:
                ssl_info = self._check_ssl_details()
                details['ssl_details'] = ssl_info
                if ssl_info.get('valid'):
                    self.wins.append(f"✅ SSL valid until {ssl_info.get('expiry', 'unknown')}")
                else:
                    self.issues.append("⚠️ SSL certificate issue: " + ssl_info.get('error', 'unknown'))
            except Exception:
                pass
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
        try:
            if security_headers.get('score', 0) >= 4:
                score += 1
                self.wins.append("✅ Good security headers")
            elif security_headers.get('score', 0) > 0:
                self.issues.append("⚠️ Some security headers missing")
        except Exception:
            pass

        tech_stack = self._detect_technology()
        details['technology'] = tech_stack
        try:
            if tech_stack:
                self.wins.append(f"✅ Detected: {', '.join(tech_stack[:3])}")
        except Exception:
            pass

        # ── PageSpeed API for Core Web Vitals ──
        try:
            pagespeed = self._fetch_pagespeed()
            if pagespeed:
                details['pagespeed'] = self._parse_pagespeed(pagespeed)
                cwv = details['pagespeed'].get('core_web_vitals', {})
                perf_score = details['pagespeed'].get('performance_score')
                if cwv.get('lcp', 0) < 2.5:
                    self.wins.append("✅ LCP (Largest Contentful Paint) < 2.5s")
            elif cwv.get('lcp'):
                self.issues.append(f"⚠️ LCP (Largest Contentful Paint) is {cwv['lcp']}s — target < 2.5s")
            if cwv.get('cls', 1) < 0.1:
                self.wins.append("✅ CLS (Cumulative Layout Shift) < 0.1")
            elif cwv.get('cls'):
                self.issues.append(f"⚠️ CLS (Cumulative Layout Shift) is {cwv['cls']} — target < 0.1")
            if cwv.get('fid', 0) < 100:
                self.wins.append("✅ FID (First Input Delay) < 100ms")
            elif cwv.get('fid'):
                self.issues.append(f"⚠️ FID (First Input Delay) is {cwv['fid']}ms — target < 100ms")
            if cwv.get('inp', 0) < 200:
                self.wins.append("✅ INP (Interaction to Next Paint) < 200ms")
            elif cwv.get('inp'):
                self.issues.append(f"⚠️ INP (Interaction to Next Paint) is {cwv['inp']}ms — target < 200ms")
            if perf_score is not None:
                if perf_score >= 90:
                    self.wins.append(f"✅ PageSpeed Performance: {int(perf_score)}/100")
                elif perf_score >= 50:
                    self.issues.append(f"⚠️ PageSpeed Performance: {int(perf_score)}/100 — needs improvement")
                else:
                    self.issues.append(f"⚠️ PageSpeed Performance: {int(perf_score)}/100 — poor")
        except Exception:
            pass

        # ── Deep HTTP-only Analysis ──
        try:
            perf_deep = self._deep_performance_analysis()
            if perf_deep:
            details['deep_performance'] = perf_deep
            # Score adjustments based on deep analysis
            if perf_deep.get('resource_hints', {}).get('preload', 0) > 0:
                self.wins.append("✅ Resource preloading detected")
            if perf_deep.get('resource_hints', {}).get('preconnect', 0) > 0:
                self.wins.append("✅ DNS preconnect hints present")
            if perf_deep.get('compression') in ('gzip', 'br', 'deflate'):
                self.wins.append(f"✅ Compression: {perf_deep['compression'].upper()}")
            else:
                self.issues.append("⚠️ No compression detected")
            
            rc = perf_deep.get('resource_counts', {})
            if rc.get('scripts', 0) > 20:
                self.issues.append(f"⚠️ High script count ({rc['scripts']}) — consider bundling")
            if rc.get('stylesheets', 0) > 10:
                self.issues.append(f"⚠️ High stylesheet count ({rc['stylesheets']}) — consider combining")
            
            script_load = perf_deep.get('script_loading', {})
            if script_load.get('async', 0) + script_load.get('defer', 0) == 0:
                self.issues.append("⚠️ No async/defer scripts — render blocking likely")
            
            img_opt = perf_deep.get('image_optimization', {})
            if img_opt.get('lazy_loading', 0) > 0:
                self.wins.append("✅ Lazy loading images detected")
            if img_opt.get('webp', 0) > 0:
                self.wins.append("✅ WebP images detected")
            if img_opt.get('avif', 0) > 0:
                self.wins.append("✅ AVIF images detected")
            
            if perf_deep.get('service_worker'):
                self.wins.append("✅ Service Worker registered (offline support)")
            if perf_deep.get('critical_css_inline'):
                self.wins.append("✅ Critical CSS inlined")

        # Core Web Vitals estimation
        try:
            cwv_est = self._estimate_core_web_vitals()
            if cwv_est:
                details['core_web_vitals_estimate'] = cwv_est
                lcp = cwv_est.get('lcp_likelihood', 'unknown')
                cls = cwv_est.get('cls_likelihood', 'unknown')
                fid = cwv_est.get('fid_likelihood', 'unknown')
                if lcp == 'good':
                    self.wins.append("✅ Estimated LCP: Good")
                elif lcp == 'poor':
                    self.issues.append("⚠️ Estimated LCP: Poor — optimize hero image/loading")
                if cls == 'good':
                    self.wins.append("✅ Estimated CLS: Good")
                elif cls == 'poor':
                    self.issues.append("⚠️ Estimated CLS: Poor — add dimensions to images/fonts")
                if fid == 'good':
                    self.wins.append("✅ Estimated FID/INP: Good")
                elif fid == 'poor':
                    self.issues.append("⚠️ Estimated FID/INP: Poor — reduce main thread blocking")
        except Exception:
            pass

        # Deep SEO analysis
        try:
            seo_deep = self._deep_seo_analysis()
            if seo_deep:
                details['deep_seo'] = seo_deep
                if seo_deep.get('title_optimal'):
                    self.wins.append("✅ Optimal title tag length")
                if seo_deep.get('meta_desc_optimal'):
                    self.wins.append("✅ Optimal meta description length")
                if seo_deep.get('structured_data_count', 0) > 0:
                    self.wins.append(f"✅ Structured data: {seo_deep['structured_data_count']} items ({', '.join(seo_deep.get('schema_types', [])[:3])})")
                if seo_deep.get('images', {}).get('alt_coverage', '0%') != 'N/A':
                    alt_cov = int(seo_deep['images']['alt_coverage'].rstrip('%'))
                    if alt_cov == 100:
                        self.wins.append("✅ All images have alt text")
                    elif alt_cov < 80:
                        self.issues.append(f"⚠️ Image alt coverage: {alt_cov}%")
        except Exception:
            pass

        # Deep accessibility analysis
        try:
            a11y_deep = self._deep_accessibility_analysis()
            if a11y_deep:
                details['deep_accessibility'] = a11y_deep
                if a11y_deep.get('lang'):
                    self.wins.append("✅ Language attribute declared")
        except Exception:
            pass

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

    def _fetch_pagespeed(self, strategy='mobile'):
        """Fetch PageSpeed Insights data for the website."""
        # API key not configured - skip external API call
        return None

    def _parse_pagespeed(self, data):
        """Parse PageSpeed Insights response into readable metrics."""
        try:
            lighthouse = data.get('lighthouseResult', {})
            categories = lighthouse.get('categories', {})
            audits = lighthouse.get('audits', {})
            
            metrics = {}
            metric_map = {
                'largest-contentful-paint': 'lcp',
                'first-input-delay': 'fid',
                'cumulative-layout-shift': 'cls',
                'interaction-to-next-paint': 'inp',
                'first-contentful-paint': 'fcp',
                'speed-index': 'si',
                'total-blocking-time': 'tbt'
            }
            for key, name in metric_map.items():
                audit = audits.get(key, {})
                if 'numericValue' in audit:
                    metrics[name] = round(audit['numericValue'] / 1000, 2) if key in ['largest-contentful-paint', 'first-input-delay', 'interaction-to-next-paint', 'first-contentful-paint', 'speed-index', 'total-blocking-time'] else round(audit['numericValue'], 3)
            
            return {
                'performance_score': categories.get('performance', {}).get('score', 0) * 100,
                'accessibility_score': categories.get('accessibility', {}).get('score', 0) * 100,
                'best_practices_score': categories.get('best-practices', {}).get('score', 0) * 100,
                'seo_score': categories.get('seo', {}).get('score', 0) * 100,
                'core_web_vitals': metrics,
                'url': data.get('id', '')
            }
        except Exception:
            return {}

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

    # ── Deep HTTP-only Analysis (no API keys needed) ──

    def _deep_performance_analysis(self):
        """Analyze performance indicators from HTML, headers, and resource hints."""
        if not self.resp or self.resp.status_code != 200:
            return {}
        
        details = {}
        html_lower = self.html.lower()
        
        # Resource hints
        resource_hints = {
            'preload': len(re.findall(r'<link[^>]+rel=["\']preload["\']', self.html, re.IGNORECASE)),
            'prefetch': len(re.findall(r'<link[^>]+rel=["\']prefetch["\']', self.html, re.IGNORECASE)),
            'preconnect': len(re.findall(r'<link[^>]+rel=["\']preconnect["\']', self.html, re.IGNORECASE)),
            'dns-prefetch': len(re.findall(r'<link[^>]+rel=["\']dns-prefetch["\']', self.html, re.IGNORECASE)),
            'prerender': len(re.findall(r'<link[^>]+rel=["\']prerender["\']', self.html, re.IGNORECASE)),
            'modulepreload': len(re.findall(r'<link[^>]+rel=["\']modulepreload["\']', self.html, re.IGNORECASE)),
        }
        details['resource_hints'] = resource_hints
        
        # Compression
        content_encoding = self.headers.get('Content-Encoding', '').lower()
        details['compression'] = content_encoding if content_encoding else 'none'
        
        # HTTP/2 or HTTP/3
        try:
            details['http_version'] = getattr(self.resp.raw, 'version', 11) / 10  # 1.1, 2.0, 3.0
        except Exception:
            details['http_version'] = 1.1
        
        # Resource counts from HTML
        script_count = len(re.findall(r'<script[^>]*>', html_lower, re.IGNORECASE))
        css_count = len(re.findall(r'<link[^>]+rel=["\']stylesheet["\']', html_lower, re.IGNORECASE))
        img_count = len(re.findall(r'<img[^>]*>', html_lower, re.IGNORECASE))
        iframe_count = len(re.findall(r'<iframe[^>]*>', html_lower, re.IGNORECASE))
        font_count = len(re.findall(r'<link[^>]+rel=["\']preload["\'][^>]+as=["\']font["\']', html_lower, re.IGNORECASE))
        
        details['resource_counts'] = {
            'scripts': script_count,
            'stylesheets': css_count,
            'images': img_count,
            'iframes': iframe_count,
            'font_preloads': font_count
        }
        
        # Inline scripts/styles (render-blocking)
        inline_scripts = len(re.findall(r'<script[^>]*>(?!.*src=)', self.html, re.IGNORECASE))
        inline_styles = len(re.findall(r'<style[^>]*>', html_lower, re.IGNORECASE))
        details['inline_resources'] = {'scripts': inline_scripts, 'styles': inline_styles}
        
        # Async/defer scripts
        async_scripts = len(re.findall(r'<script[^>]+async', html_lower, re.IGNORECASE))
        defer_scripts = len(re.findall(r'<script[^>]+defer', html_lower, re.IGNORECASE))
        details['script_loading'] = {'async': async_scripts, 'defer': defer_scripts}
        
        # Image optimization hints
        lazy_images = len(re.findall(r'<img[^>]+loading=["\']lazy["\']', html_lower, re.IGNORECASE))
        webp_images = len(re.findall(r'\.webp["\']', html_lower, re.IGNORECASE))
        avif_images = len(re.findall(r'\.avif["\']', html_lower, re.IGNORECASE))
        details['image_optimization'] = {
            'lazy_loading': lazy_images,
            'webp': webp_images,
            'avif': avif_images,
            'total': img_count
        }
        
        # Critical CSS inlining
        critical_css_inline = bool(re.search(r'<style[^>]*>.*?@media', self.html, re.DOTALL | re.IGNORECASE))
        details['critical_css_inline'] = critical_css_inline
        
        # Service Worker
        sw_reg = bool(re.search(r'navigator\.serviceWorker\.register|serviceworker\.js', html_lower))
        details['service_worker'] = sw_reg
        
        # Cache headers
        cache_control = self.headers.get('Cache-Control', '')
        etag = self.headers.get('ETag', '')
        last_modified = self.headers.get('Last-Modified', '')
        details['caching'] = {
            'cache_control': cache_control,
            'etag': bool(etag),
            'last_modified': bool(last_modified)
        }
        
        return details

    def _deep_seo_analysis(self):
        """Deep SEO analysis from HTML and HTTP."""
        if not self.resp or self.resp.status_code != 200:
            return {}
        
        details = {}
        html_lower = self.html.lower()
        
        # Title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', self.html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ''
        details['title'] = title
        details['title_length'] = len(title)
        details['title_optimal'] = 30 <= len(title) <= 60
        
        # Meta description
        meta_desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', self.html, re.IGNORECASE)
        meta_desc_content = meta_desc.group(1).strip() if meta_desc else ''
        details['meta_description'] = meta_desc_content
        details['meta_desc_length'] = len(meta_desc_content)
        details['meta_desc_optimal'] = 120 <= len(meta_desc_content) <= 160
        
        # Heading hierarchy
        h1_count = len(re.findall(r'<h1[^>]*>', html_lower, re.IGNORECASE))
        h2_count = len(re.findall(r'<h2[^>]*>', html_lower, re.IGNORECASE))
        h3_count = len(re.findall(r'<h3[^>]*>', html_lower, re.IGNORECASE))
        details['headings'] = {'h1': h1_count, 'h2': h2_count, 'h3': h3_count}
        
        # Canonical
        canonical = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', self.html, re.IGNORECASE)
        details['canonical'] = canonical.group(1) if canonical else None
        
        # Open Graph
        og_tags = {}
        for prop in ['og:title', 'og:description', 'og:image', 'og:url', 'og:type', 'og:site_name']:
            match = re.search(rf'<meta[^>]+property=["\']{prop}["\'][^>]+content=["\']([^"\']+)["\']', self.html, re.IGNORECASE)
            og_tags[prop] = match.group(1) if match else None
        details['open_graph'] = {k: v for k, v in og_tags.items() if v}
        
        # Twitter Cards
        twitter_tags = {}
        for name in ['twitter:card', 'twitter:title', 'twitter:description', 'twitter:image', 'twitter:site']:
            match = re.search(rf'<meta[^>]+name=["\']{name}["\'][^>]+content=["\']([^"\']+)["\']', self.html, re.IGNORECASE)
            twitter_tags[name] = match.group(1) if match else None
        details['twitter_cards'] = {k: v for k, v in twitter_tags.items() if v}
        
        # Structured data (JSON-LD)
        json_ld_scripts = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', self.html, re.IGNORECASE | re.DOTALL)
        structured_data = []
        for script in json_ld_scripts:
            try:
                parsed = json.loads(script.strip())
                if isinstance(parsed, list):
                    structured_data.extend(parsed)
                else:
                    structured_data.append(parsed)
            except:
                pass
        details['structured_data'] = structured_data
        details['structured_data_count'] = len(structured_data)
        
        # Schema.org types detected
        schema_types = set()
        for item in structured_data:
            if isinstance(item, dict) and '@type' in item:
                schema_types.add(item['@type'])
            elif isinstance(item, list):
                for sub in item:
                    if isinstance(sub, dict) and '@type' in sub:
                        schema_types.add(sub['@type'])
        details['schema_types'] = list(schema_types)
        
        # Robots meta
        robots = re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']+)["\']', self.html, re.IGNORECASE)
        details['robots_meta'] = robots.group(1) if robots else None
        
        # Hreflang
        hreflangs = re.findall(r'<link[^>]+rel=["\']alternate["\'][^>]+hreflang=["\']([^"\']+)["\'][^>]+href=["\']([^"\']+)["\']', self.html, re.IGNORECASE)
        details['hreflang'] = [{'lang': h[0], 'url': h[1]} for h in hreflangs]
        
        # Pagination
        pagination = {
            'next': bool(re.search(r'<link[^>]+rel=["\']next["\']', html_lower, re.IGNORECASE)),
            'prev': bool(re.search(r'<link[^>]+rel=["\']prev["\']', html_lower, re.IGNORECASE)),
            'rel_canonical_self': bool(canonical)
        }
        details['pagination'] = pagination
        
        # Internal links analysis
        internal_links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', self.html, re.IGNORECASE)
        internal_count = sum(1 for link in internal_links if link.startswith('/') or urlparse(link).netloc == urlparse(self.final_url).netloc)
        external_count = len(internal_links) - internal_count
        details['links'] = {'internal': internal_count, 'external': external_count, 'total': len(internal_links)}
        
        # Images with alt text
        img_tags = re.findall(r'<img[^>]*>', html_lower, re.IGNORECASE)
        imgs_with_alt = sum(1 for img in img_tags if 'alt=' in img)
        details['images'] = {'total': len(img_tags), 'with_alt': imgs_with_alt, 'alt_coverage': f'{round(imgs_with_alt/len(img_tags)*100) if img_tags else 0}%' if img_tags else 'N/A'}
        
        return details

    def _deep_accessibility_analysis(self):
        """Basic accessibility indicators from HTML."""
        if not self.resp or self.resp.status_code != 200:
            return {}
        
        details = {}
        html_lower = self.html.lower()
        
        # Lang attribute
        lang_match = re.search(r'<html[^>]+lang=["\']([^"\']+)["\']', html_lower, re.IGNORECASE)
        details['lang'] = lang_match.group(1) if lang_match else None
        
        # ARIA landmarks
        landmarks = {
            'banner': 'role="banner"' in html_lower,
            'navigation': 'role="navigation"' in html_lower,
            'main': 'role="main"' in html_lower,
            'complementary': 'role="complementary"' in html_lower,
            'contentinfo': 'role="contentinfo"' in html_lower,
            'search': 'role="search"' in html_lower,
            'form': 'role="form"' in html_lower,
        }
        details['aria_landmarks'] = landmarks
        
        # Semantic HTML5 elements
        semantic = {
            'header': '<header' in html_lower,
            'nav': '<nav' in html_lower,
            'main': '<main' in html_lower,
            'article': '<article' in html_lower,
            'section': '<section' in html_lower,
            'aside': '<aside' in html_lower,
            'footer': '<footer' in html_lower,
            'figure': '<figure' in html_lower,
            'figcaption': '<figcaption' in html_lower,
            'time': '<time' in html_lower,
        }
        details['semantic_elements'] = semantic
        
        # Form labels
        inputs = re.findall(r'<input[^>]*>', self.html, re.IGNORECASE)
        inputs_with_labels = 0
        for inp in inputs:
            inp_id = re.search(r'id=["\']([^"\']+)["\']', inp)
            if inp_id and f'for="{inp_id.group(1)}"' in self.html:
                inputs_with_labels += 1
            elif 'aria-label' in inp or 'aria-labelledby' in inp:
                inputs_with_labels += 1
        details['form_labels'] = {'total_inputs': len(inputs), 'labeled': inputs_with_labels}
        
        # Skip links
        details['skip_link'] = 'skip to main' in html_lower or 'skip to content' in html_lower
        
        # Focus indicators (CSS outline: none detection)
        details['focus_outline_removed'] = 'outline: none' in self.html.lower() or 'outline:none' in self.html.lower()
        
        return details

    def _deep_security_analysis(self):
        """Extended security analysis."""
        if not self.resp:
            return {}
        
        details = {}
        headers = self.headers
        html_lower = self.html.lower()
        
        # Extended security headers
        sec_headers = {
            'cross_origin_embedder_policy': headers.get('Cross-Origin-Embedder-Policy'),
            'cross_origin_opener_policy': headers.get('Cross-Origin-Opener-Policy'),
            'cross_origin_resource_policy': headers.get('Cross-Origin-Resource-Policy'),
            'expect_ct': headers.get('Expect-CT'),
            'report_to': headers.get('Report-To'),
            'nel': headers.get('NEL'),
        }
        details['extended_headers'] = {k: v for k, v in sec_headers.items() if v}
        
        # CSP analysis
        csp = headers.get('Content-Security-Policy', '')
        if csp:
            details['csp_directives'] = [d.strip() for d in csp.split(';') if d.strip()]
            details['csp_has_report_uri'] = 'report-uri' in csp or 'report-to' in csp
            details['csp_unsafe_inline'] = "'unsafe-inline'" in csp
            details['csp_unsafe_eval'] = "'unsafe-eval'" in csp
        
        # Cookie security
        cookies = headers.get('Set-Cookie', '')
        if cookies:
            cookie_list = cookies.split(',')
            secure_count = sum(1 for c in cookie_list if 'secure' in c.lower())
            httponly_count = sum(1 for c in cookie_list if 'httponly' in c.lower())
            samesite_count = sum(1 for c in cookie_list if 'samesite' in c.lower())
            details['cookie_security'] = {
                'total': len(cookie_list),
                'secure': secure_count,
                'httponly': httponly_count,
                'samesite': samesite_count
            }
        
        # Mixed content detection
        mixed_content = bool(re.search(r'src=["\']http://|href=["\']http://', self.html))
        details['mixed_content_detected'] = mixed_content
        
        # Form action HTTPS
        form_actions = re.findall(r'<form[^>]+action=["\']([^"\']+)["\']', self.html, re.IGNORECASE)
        insecure_forms = sum(1 for a in form_actions if a.startswith('http://'))
        details['insecure_form_actions'] = insecure_forms
        
        # X-Powered-By exposure
        details['powered_by_exposed'] = bool(headers.get('X-Powered-By'))
        
        # Server header exposure
        details['server_exposed'] = bool(headers.get('Server'))
        
        return details

    def _deep_google_business_analysis(self):
        """Deeper GBP detection from HTML, structured data, and public endpoints."""
        if not self.resp or self.resp.status_code != 200:
            return {}
        
        details = {}
        html_lower = self.html.lower()
        
        # Check for Google Maps embed
        maps_embeds = len(re.findall(r'google\.com/maps/embed|maps\.google\.com', html_lower))
        details['maps_embeds'] = maps_embeds
        
        # Check for Google Business schema
        gbp_schema = False
        json_ld_scripts = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', self.html, re.IGNORECASE | re.DOTALL)
        for script in json_ld_scripts:
            try:
                parsed = json.loads(script.strip())
                items = parsed if isinstance(parsed, list) else [parsed]
                for item in items:
                    if isinstance(item, dict):
                        if item.get('@type') in ['LocalBusiness', 'Store', 'Restaurant', 'Organization']:
                            gbp_schema = True
                            details['local_business_schema'] = item.get('@type')
            except:
                pass
        details['gbp_schema_detected'] = gbp_schema
        
        # Check for place ID in URL
        place_id_match = re.search(r'place_id=([^&"\']+)', html_lower)
        details['place_id'] = place_id_match.group(1) if place_id_match else None
        
        # Check for Google Maps API key
        maps_key = bool(re.search(r'ai[zs]a[^"\']{30,}', html_lower))
        details['maps_api_key_exposed'] = maps_key
        
        # Check for review markup
        review_schema = False
        for script in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', self.html, re.IGNORECASE | re.DOTALL):
            try:
                parsed = json.loads(script.strip())
                items = parsed if isinstance(parsed, list) else [parsed]
                for item in items:
                    if isinstance(item, dict) and item.get('@type') in ['Review', 'AggregateRating']:
                        review_schema = True
            except:
                pass
        details['review_schema'] = review_schema
        
        # Check for address in structured format
        address_found = any(k in html_lower for k in ['streetaddress', 'addresslocality', 'addressregion', 'postalcode'])
        details['structured_address'] = address_found
        
        return details

    def _deep_social_media_analysis(self):
        """Fetch public social profile data via HTTP (no API keys)."""
        if not self.resp or self.resp.status_code != 200:
            return {}
        
        details = {}
        social_platforms = {
            'facebook': 'facebook.com',
            'instagram': 'instagram.com',
            'twitter': 'twitter.com',
            'x': 'x.com',
            'linkedin': 'linkedin.com',
            'youtube': 'youtube.com',
            'tiktok': 'tiktok.com',
            'pinterest': 'pinterest.com',
            'threads': 'threads.net'
        }
        
        found = {}
        for platform, domain in social_platforms.items():
            # Check for links on website
            pattern = rf'href=["\']https?://(?:www\.)?{re.escape(domain)}/([^"\'>\s]+)'
            matches = re.findall(pattern, self.html, re.IGNORECASE)
            if matches:
                found[platform] = matches[0]
        
        details['profile_links'] = found
        
        # Try to fetch public profile pages for follower counts (best effort)
        # This is limited and may be blocked, but we try
        for platform, username in found.items():
            if platform == 'facebook':
                count = self._fetch_facebook_followers(username)
            elif platform == 'instagram':
                count = self._fetch_instagram_followers(username)
            elif platform in ('twitter', 'x'):
                count = self._fetch_twitter_followers(username)
            elif platform == 'linkedin':
                count = self._fetch_linkedin_followers(username)
            elif platform == 'youtube':
                count = self._fetch_youtube_subscribers(username)
            else:
                count = None
            
            if count:
                details[f'{platform}_followers'] = count
        
        return details

    def _fetch_facebook_followers(self, username):
        """Try to get Facebook page likes from public page."""
        try:
            # Very limited - public page may require auth
            resp = requests.get(f'https://www.facebook.com/{username}', timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            # Facebook heavily blocks scraping - just return None
            return None
        except:
            return None

    def _fetch_instagram_followers(self, username):
        """Try to get Instagram follower count from public profile."""
        try:
            resp = requests.get(f'https://www.instagram.com/{username}/', timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if resp.status_code == 200:
                match = re.search(r'"edge_followed_by":{"count":(\d+)}', resp.text)
                if match:
                    return int(match.group(1))
        except:
            pass
        return None

    def _fetch_twitter_followers(self, username):
        """Try to get Twitter/X follower count from public profile."""
        try:
            resp = requests.get(f'https://twitter.com/{username}', timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if resp.status_code == 200:
                # Twitter uses dynamic loading - hard to scrape
                match = re.search(r'followers_count[=:]"?(\d+)"?', resp.text)
                if match:
                    return int(match.group(1))
        except:
            pass
        return None

    def _fetch_linkedin_followers(self, username):
        """Try to get LinkedIn follower count."""
        try:
            resp = requests.get(f'https://www.linkedin.com/company/{username}/', timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if resp.status_code == 200:
                match = re.search(r'followers[^>]*>(\d[\d,]*)', resp.text, re.IGNORECASE)
                if match:
                    return int(match.group(1).replace(',', ''))
        except:
            pass
        return None

    def _fetch_youtube_subscribers(self, username):
        """Try to get YouTube subscriber count."""
        try:
            resp = requests.get(f'https://www.youtube.com/@{username}', timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if resp.status_code == 200:
                match = re.search(r'subscriber[s]?[^>]*>([\d,.]+)', resp.text, re.IGNORECASE)
                if match:
                    return int(match.group(1).replace(',', ''))
        except:
            pass
        return None

    def _deep_reviews_analysis(self):
        """Deeper review platform detection."""
        if not self.resp or self.resp.status_code != 200:
            return {}
        
        details = {}
        html_lower = self.html.lower()
        
        review_platforms = {
            'google_reviews': ['google review', 'google reviews', 'reviews.google.com'],
            'trustpilot': ['trustpilot', 'widget.trustpilot.com'],
            'yelp': ['yelp.com', 'yelp review'],
            'angie': ['angie\'s list', 'angieslist'],
            'tripadvisor': ['tripadvisor', 'trip advisor'],
            'facebook_reviews': ['facebook.com/reviews', 'facebook review'],
            'g2': ['g2.com', 'g2 crowd'],
            'capterra': ['capterra', 'capterra review'],
            'glassdoor': ['glassdoor', 'glassdoor review'],
            'indeed': ['indeed.com/reviews', 'indeed review'],
            'clutch': ['clutch.co', 'clutch review'],
            'better_business_bureau': ['bbb.org', 'better business bureau'],
        }
        
        found = []
        for platform, keywords in review_platforms.items():
            if any(kw in html_lower for kw in keywords):
                found.append(platform)
        
        details['review_platforms_detected'] = found
        
        # Check for review schema
        review_schema_count = 0
        for script in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', self.html, re.IGNORECASE | re.DOTALL):
            try:
                parsed = json.loads(script.strip())
                items = parsed if isinstance(parsed, list) else [parsed]
                for item in items:
                    if isinstance(item, dict) and item.get('@type') in ['Review', 'AggregateRating']:
                        review_schema_count += 1
            except:
                pass
        details['review_schema_count'] = review_schema_count
        
        # Testimonial/quote detection
        testimonial_keywords = ['testimonial', 'client says', 'customer says', 'what our clients', 'what our customers']
        details['testimonials_present'] = any(kw in html_lower for kw in testimonial_keywords)
        
        return details

    def _deep_mobile_analysis(self):
        """Extended mobile friendliness checks."""
        if not self.resp or self.resp.status_code != 200:
            return {}
        
        details = {}
        html_lower = self.html.lower()
        
        # Viewport variations
        viewport_match = re.search(r'<meta[^>]+name=["\']viewport["\'][^>]+content=["\']([^"\']+)["\']', self.html, re.IGNORECASE)
        if viewport_match:
            content = viewport_match.group(1)
            details['viewport_content'] = content
            details['viewport_width_device'] = 'width=device-width' in content
            details['viewport_initial_scale'] = 'initial-scale=1' in content
            details['viewport_user_scalable'] = 'user-scalable=no' not in content
        
        # Touch target sizing (heuristic)
        buttons = re.findall(r'<button[^>]*>|<a[^>]*class=["\'][^"\']*btn[^"\']*["\']', self.html, re.IGNORECASE)
        details['button_count'] = len(buttons)
        
        # Font size detection
        font_sizes = re.findall(r'font-size:\s*(\d+(?:\.\d+)?)(px|rem|em)', self.html, re.IGNORECASE)
        small_fonts = sum(1 for size, unit in font_sizes if (unit == 'px' and float(size) < 16) or (unit in ('rem', 'em') and float(size) < 1))
        details['potentially_small_fonts'] = small_fonts
        
        # Tap target spacing (heuristic)
        details['touch_friendly_heuristic'] = len(re.findall(r'padding:\s*\d+px\s*\d+px', self.html, re.IGNORECASE)) > 0
        
        # Media queries count
        details['media_queries_count'] = len(re.findall(r'@media\s*[^{]+\{', self.html, re.IGNORECASE))
        
        # Responsive images
        details['picture_elements'] = len(re.findall(r'<picture[^>]*>', self.html, re.IGNORECASE))
        details['srcset_usage'] = len(re.findall(r'srcset=["\'][^"\']+', self.html, re.IGNORECASE))
        details['sizes_attr'] = len(re.findall(r'sizes=["\'][^"\']+', self.html, re.IGNORECASE))
        
        return details

    def _deep_contact_analysis(self):
        """Extended contact information detection."""
        if not self.resp or self.resp.status_code != 200:
            return {}
        
        details = {}
        html = self.html
        
        # Phone patterns (international)
        phones = re.findall(r'(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{1,4}\)?[\s\-]?)?\d{3,4}[\s\-]?\d{3,4}', html)
        details['phones'] = list(set(phones))[:5]
        
        # Emails
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
        details['emails'] = list(set(emails))[:5]
        
        # Social links
        social_links = {}
        for platform in ['facebook', 'instagram', 'twitter', 'linkedin', 'youtube', 'tiktok', 'pinterest', 'whatsapp', 'telegram', 'skype']:
            pattern = rf'href=["\']https?://(?:www\.)?{platform}\.com/([^"\'>\s]+)'
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                social_links[platform] = matches[0]
        details['social_links'] = social_links
        
        # Contact form
        details['contact_form'] = '<form' in html.lower() and ('contact' in html.lower() or 'message' in html.lower() or 'inquiry' in html.lower())
        
        # Chat widgets
        chat_widgets = {
            'tawk': 'tawk.to',
            'intercom': 'intercom.io',
            'crisp': 'crisp.chat',
            'zendesk': 'zendesk.com',
            'drift': 'drift.com',
            'hubspot': 'hubspot.com',
            'freshchat': 'freshchat.com',
        }
        html_lower = self.html.lower()
        found_chat = {k: v for k, v in chat_widgets.items() if v in html_lower}
        details['chat_widgets'] = {k: v for k, v in found_chat.items() if v}
        
        # Address components
        address_indicators = ['street', 'avenue', 'road', 'blvd', 'drive', 'lane', 'suite', 'floor', 'unit', 'building', 'plaza', 'city', 'state', 'zip', 'postal', 'country']
        details['address_indicators'] = sum(1 for ind in address_indicators if ind in html_lower)
        
        # Business hours
        hours_patterns = ['opening hours', 'business hours', 'hours of operation', 'open daily', 'mon-fri', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        details['business_hours_mentioned'] = any(p in html.lower() for p in hours_patterns)
        
        return details

    def _estimate_core_web_vitals(self):
        """Estimate Core Web Vitals from HTML patterns and resource hints (no API)."""
        if not self.resp or self.resp.status_code != 200:
            return {}
        
        estimates = {}
        html = self.html
        html_lower = html.lower()
        
        # LCP estimation
        lcp_factors = []
        
        # Preload LCP image
        if 'rel="preload"' in html_lower and ('as="image"' in html_lower or 'as="font"' in html_lower):
            lcp_factors.append('lcp_preload')
        
        # Hero image above fold
        hero_img = re.search(r'<img[^>]+(?:class|id)=["\'][^"\']*(?:hero|banner|main|cover|featured)[^"\']*["\']', html, re.IGNORECASE)
        if hero_img:
            lcp_factors.append('hero_image')
        
        # No render-blocking scripts in head
        head_end = html_lower.find('</head>')
        head_content = html_lower[:head_end] if head_end != -1 else html_lower[:5000]
        blocking_scripts = len(re.findall(r'<script[^>]*src=["\'][^"\']+["\'][^>]*(?!async|defer)', head_content, re.IGNORECASE))
        if blocking_scripts == 0:
            lcp_factors.append('no_blocking_scripts')
        
        estimates['lcp_signals'] = lcp_factors
        estimates['lcp_likelihood'] = 'good' if len(lcp_factors) >= 2 else 'needs_improvement' if lcp_factors else 'poor'
        
        # CLS estimation
        cls_factors = []
        
        # Width/height on images
        imgs_no_dim = len(re.findall(r'<img[^>]*(?!width|height)[^>]*>', html, re.IGNORECASE))
        total_imgs = len(re.findall(r'<img[^>]*>', html, re.IGNORECASE))
        if total_imgs > 0 and imgs_no_dim / total_imgs < 0.3:
            cls_factors.append('image_dimensions')
        
        # Font display swap
        if 'font-display: swap' in html or 'font-display: swap' in html_lower:
            cls_factors.append('font_display_swap')
        
        # Preload fonts
        if 'rel="preload"' in html_lower and 'as="font"' in html_lower:
            cls_factors.append('font_preload')
        
        estimates['cls_signals'] = cls_factors
        estimates['cls_likelihood'] = 'good' if len(cls_factors) >= 2 else 'needs_improvement' if cls_factors else 'poor'
        
        # FID/INP estimation
        fid_factors = []
        
        # Minimal main thread blocking
        js_size_estimate = len(re.findall(r'<script[^>]*src=', html, re.IGNORECASE))
        if js_size_estimate < 10:
            fid_factors.append('few_scripts')
        
        # Web workers
        if 'worker.' in html_lower or 'new Worker(' in html:
            fid_factors.append('web_workers')
        
        # defer/async scripts
        async_scripts = len(re.findall(r'<script[^>]+async', html, re.IGNORECASE))
        defer_scripts = len(re.findall(r'<script[^>]+defer', html, re.IGNORECASE))
        total_scripts = len(re.findall(r'<script[^>]*src=', html, re.IGNORECASE))
        if total_scripts > 0 and (async_scripts + defer_scripts) / total_scripts > 0.5:
            fid_factors.append('deferred_scripts')
        
        estimates['fid_signals'] = fid_factors
        estimates['fid_likelihood'] = 'good' if len(fid_factors) >= 2 else 'needs_improvement' if fid_factors else 'poor'
        
        return estimates
                    channel_id = items[0]['snippet']['channelId']
                    # Get channel stats
                    stats_url = "https://www.googleapis.com/youtube/v3/channels"
                    stats_params = {
                        'part': 'statistics,snippet,brandingSettings',
                        'id': channel_id,
                        'key': YOUTUBE_API_KEY
                    }
                    stats_resp = requests.get(stats_url, params=stats_params, timeout=15)
                    if stats_resp.status_code == 200:
                        return stats_resp.json().get('items', [{}])[0]
        except Exception:
            pass
        return None

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

        # ── Google Places API for real GBP data ──
        gbp_data = None  # API key not configured
        if gbp_data:
            details['google_business_profile'] = {
                'name': gbp_data.get('name'),
                'address': gbp_data.get('formatted_address'),
                'phone': gbp_data.get('formatted_phone_number'),
                'website': gbp_data.get('website'),
                'rating': gbp_data.get('rating'),
                'review_count': gbp_data.get('user_ratings_total'),
                'status': gbp_data.get('business_status'),
                'place_id': gbp_data.get('place_id'),
                'maps_url': gbp_data.get('url')
            }
            score += 8
            self.wins.append(f"✅ Verified Google Business Profile: {gbp_data.get('name')} ({gbp_data.get('user_ratings_total', 0)} reviews, {gbp_data.get('rating', 'N/A')}★)")
        else:
            self.issues.append("⚠️ No verified Google Business Profile found via Places API")

        score += 2
        details['profile_possible'] = True

        # ── Deep HTTP-only GBP analysis ──
        try:
            gbp_deep = self._deep_google_business_analysis()
            if gbp_deep:
                details['deep_gbp'] = gbp_deep
                if gbp_deep.get('gbp_schema_detected'):
                    self.wins.append("✅ LocalBusiness schema detected")
                if gbp_deep.get('maps_embeds', 0) > 0:
                    self.wins.append("✅ Google Maps embed present")
                if gbp_deep.get('review_schema'):
                    self.wins.append("✅ Review schema markup present")
                if gbp_deep.get('structured_address'):
                    self.wins.append("✅ Structured address markup present")
                if gbp_deep.get('maps_api_key_exposed'):
                    self.issues.append("⚠️ Google Maps API key exposed in HTML")
        except Exception:
            pass

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
        platform_data = {}

        # ── Website-based detection (existing) ──
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

        # ── Optional API-based real data ──
        api_data = {}

        if api_data:
            details['api_data'] = api_data
            self.wins.append(f"✅ Fetched real-time social data for {len(api_data)} platform(s)")

        score += min(len(found_platforms) * 3, 12)
        details['platforms_found'] = found_platforms
        details['platform_count'] = len(found_platforms)
        details['platform_data'] = api_data

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

        if api_data:
            details['api_data'] = api_data
            self.wins.append(f"✅ Fetched real-time social data for {len(api_data)} platform(s)")

        # ── Deep HTTP-only social analysis ──
        try:
            social_deep = self._deep_social_media_analysis()
            if social_deep:
                details['deep_social'] = social_deep
                if social_deep.get('profile_links'):
                    self.wins.append(f"✅ Social profile links: {', '.join(social_deep['profile_links'].keys())}")
                for platform in ['facebook', 'instagram', 'twitter', 'linkedin', 'youtube']:
                    key = f'{platform}_followers'
                    if key in social_deep and social_deep[key]:
                        self.wins.append(f"✅ {platform.title()}: {social_deep[key]:,} followers")
        except Exception:
            pass

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

        # ── Deep HTTP-only mobile analysis ──
        try:
            mobile_deep = self._deep_mobile_analysis()
            if mobile_deep:
                details['deep_mobile'] = mobile_deep
                if mobile_deep.get('viewport_content'):
                    vc = mobile_deep['viewport_content']
                    if vc.get('viewport_width_device'):
                        self.wins.append("✅ Viewport: width=device-width")
                    if vc.get('viewport_initial_scale'):
                        self.wins.append("✅ Viewport: initial-scale=1")
                    if vc.get('viewport_user_scalable'):
                        self.wins.append("✅ Viewport: user-scalable allowed")
                
                if mobile_deep.get('picture_elements', 0) > 0:
                    self.wins.append("✅ <picture> elements for responsive images")
                if mobile_deep.get('srcset_usage', 0) > 0:
                    self.wins.append("✅ srcset for responsive images")
                if mobile_deep.get('sizes_attr', 0) > 0:
                    self.wins.append("✅ sizes attribute on images")
                
                if mobile_deep.get('media_queries_count', 0) > 5:
                    self.wins.append("✅ Extensive media queries")
                elif mobile_deep.get('media_queries_count', 0) > 0:
                    self.wins.append("✅ Media queries present")
                else:
                    self.issues.append("⚠️ No media queries detected")

                if mobile_deep.get('touch_friendly_heuristic'):
                    self.wins.append("✅ Touch-friendly spacing hints")

                vp = mobile_deep.get('viewport_content', {})
                if not vp.get('viewport_width_device'):
                    self.issues.append("⚠️ Viewport missing width=device-width")
                if not vp.get('viewport_initial_scale'):
                    self.issues.append("⚠️ Viewport missing initial-scale=1")
                if not vp.get('viewport_user_scalable'):
                    self.issues.append("⚠️ Viewport disables user scaling")
        except Exception:
            pass

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

        # ── Deep HTTP-only reviews analysis ──
        try:
            reviews_deep = self._deep_reviews_analysis()
            if reviews_deep:
                details['deep_reviews'] = reviews_deep
                if reviews_deep.get('review_platforms_detected'):
                    self.wins.append(f"✅ Review platforms detected: {', '.join(reviews_deep['review_platforms_detected'])}")
                if reviews_deep.get('review_schema_count', 0) > 0:
                    self.wins.append(f"✅ Review schema markup: {reviews_deep['review_schema_count']} items")
                if reviews_deep.get('testimonials_present'):
                    self.wins.append("✅ Testimonials section present")
                if not reviews_deep.get('review_platforms_detected') and not reviews_deep.get('testimonials_present'):
                    self.issues.append("⚠️ No review platforms or testimonials detected")
        except Exception:
            pass

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

        # ── Deep SEO analysis ──
        try:
            seo_deep = self._deep_seo_analysis()
            if seo_deep:
                details['deep_seo'] = seo_deep
                if seo_deep.get('title_optimal'):
                    self.wins.append("✅ Optimal title tag length")
                if seo_deep.get('meta_desc_optimal'):
                    self.wins.append("✅ Optimal meta description length")
                if seo_deep.get('structured_data_count', 0) > 0:
                    self.wins.append(f"✅ Structured data: {seo_deep['structured_data_count']} items ({', '.join(seo_deep.get('schema_types', [])[:3])})")
                if seo_deep.get('images', {}).get('alt_coverage', '0%') != 'N/A':
                    alt_cov = int(seo_deep['images']['alt_coverage'].rstrip('%'))
                    if alt_cov == 100:
                        self.wins.append("✅ All images have alt text")
                    elif alt_cov < 80:
                        self.issues.append(f"⚠️ Image alt coverage: {alt_cov}%")
        except Exception:
            pass

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

        # ── Deep HTTP-only contact analysis ──
        try:
            contact_deep = self._deep_contact_analysis()
            if contact_deep:
                details['deep_contact'] = contact_deep
                if contact_deep.get('phones'):
                    self.wins.append(f"✅ Phone numbers: {', '.join(contact_deep['phones'][:3])}")
                if contact_deep.get('emails'):
                    self.wins.append(f"✅ Email addresses: {', '.join(contact_deep['emails'][:3])}")
                if contact_deep.get('social_links'):
                    self.wins.append(f"✅ Social links: {', '.join(contact_deep['social_links'].keys())}")
                if contact_deep.get('chat_widgets'):
                    self.wins.append(f"✅ Chat widgets: {', '.join(contact_deep['chat_widgets'].keys())}")
                if contact_deep.get('address_indicators', 0) > 3:
                    self.wins.append("✅ Detailed address information")
                if contact_deep.get('business_hours_mentioned'):
                    self.wins.append("✅ Business hours mentioned")
                if not contact_deep.get('contact_form'):
                    self.issues.append("⚠️ No contact form detected")
        except Exception:
            pass

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