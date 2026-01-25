import re
import json
import logging
from urllib.parse import urlparse
from typing import Optional, Dict, Any, Union
from redirect_tracker import RedirectTracker

logger = logging.getLogger(__name__)

class DomainFR:
    def __init__(self, homepage: str, forced_method: Optional[str] = None):
        self._homepage = homepage
        self._forced_method = forced_method
        self.tracker = RedirectTracker()

    @property
    def homepage(self) -> str:
        return self._homepage

    @homepage.setter
    def homepage(self, value: str):
        self._homepage = value

    def detect_language(self, content: str) -> Union[Dict[str, str], bool]:
        """
        Analyzes HTML content to detect French language using regex.
        Returns {'method': '...', 'value': '...'} or False.
        """
        # Base regex for handling conditional comments and HTML tag (Legacy IE stuff)
        # Ported from TS: (?:<!--\[if[^>]*>(?:<!--)?[^<]*<html[^>]*>(?:(?:<!--)?<!\[endif\]-->)?[^<]*)*(?:<!--\[if[^>]*!\\(?ie\\)?\\]><!-->)
        regex_lang_part = r"(?:<!--\[if[^>]*>(?:<!--)?[^<]*<html[^>]*>(?:(?:<!--)?<!\[endif\]-->)?[^<]*)*(?:<!--\[if[^>]*!\(?ie\)?\\]><!-->)"
        
        # Match lang attribute in HTML tag
        # Ported from TS: \s*<html[^>]*\s(?:xml:)?lang=["']?([a-zA-Z-]+)["']?
        regex_html_part = r"\s*<html[^>]*\s(?:xml:)?lang=[\"']?([a-zA-Z-]+)[\"']?"

        # 1. Combine conditional comments and HTML lang patterns
        regex_lang_html = re.compile(f"{regex_lang_part}{regex_html_part}", re.IGNORECASE)
        
        # 2. Check HTML tag without conditional comments (simpler fallback)
        regex_lang_html_simple = re.compile(f"{regex_lang_part}?{regex_html_part}", re.IGNORECASE)

        # 3. Match Open Graph locale meta tag
        regex_meta_lang = re.compile(
            r"<meta[^>]*\sproperty=[\"']og:locale[\"'][^>]*content=[\"']([a-zA-Z-]+)[\"']", 
            re.IGNORECASE
        )
        
        # 4. Match meta tag with property name="language"
        regex_meta_language = re.compile(
            r"<meta[^>]*\sname=[\"']LANGUAGE[\"'][^>]*content=[\"']([a-zA-Z-]+)[\"']", 
            re.IGNORECASE
        )

        # 5. Match HTTP-EQUIV content language meta tag
        regex_http_equiv = re.compile(
            r"<meta[^>]*\shttp-equiv=[\"']content-language[\"'][^>]*content=[\"']([a-zA-Z-]+)[\"']", 
            re.IGNORECASE
        )

        # Priority 1: Check HTML tag with conditional comments
        match_html = regex_lang_html.search(content)
        if match_html:
            return {
                "method": "langHtml",
                "value": match_html.group(1).split("-")[0]  # "fr-FR" -> "fr"
            }

        # Priority 2: Check HTML tag without conditional comments
        match_html_simple = regex_lang_html_simple.search(content)
        if match_html_simple:
            return {
                "method": "langHtml",
                "value": match_html_simple.group(1).split("-")[0]
            }

        # Priority 3: Check Open Graph locale meta tag
        match_meta = regex_meta_lang.search(content)
        if match_meta:
            return {
                "method": "matchMeta",
                "value": match_meta.group(1).split("-")[0]
            }
        
        # Priority 3.1: Check meta tag with name="language"
        match_meta_language = regex_meta_language.search(content)
        if match_meta_language:
            return {
                "method": "matchMeta",
                "value": match_meta_language.group(1).split("-")[0]
            }

        # Priority 4: Check HTTP-EQUIV content language
        match_http_equiv = regex_http_equiv.search(content)
        if match_http_equiv:
            return {
                "method": "matchHttpEquiv",
                "value": match_http_equiv.group(1).split("-")[0]
            }

        return False

    @classmethod
    async def check_url(
        cls,
        url: str,
        track_redirect: bool = True,
        proxy_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Static method to check if a URL indicates French content (TLD, path, or redirects).
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            path = parsed.path
            query = parsed.query
            
            if not hostname:
                return {"ok": False, "method": "invalid_host"}

            # Instantiate for redirect handling if needed
            instance = cls(url)

            # 1. Check TLD .fr and subdomains
            # JS: hostname.endsWith(".fr") || /^({fr|france|french|francais|français})\./i.test(hostname)
            # Simplified regex for subdomain check
            is_fr_domain = hostname.endswith(".fr") or re.search(r"^(fr|france|french|francais|français)\.", hostname, re.IGNORECASE)
            
            if is_fr_domain:
                if not track_redirect:
                    return {"ok": True, "method": "direct_match"}

                # Check if it redirects to a non-French URL (unlikely but possible) or normalize
                # In TS logic: it tracks redirects to see if final URL is still consistent
                # But here we simply follow logic
                new_url = f"{parsed.scheme}://{hostname}"
                redirections = await instance.handle_redirections(new_url, url, "", proxy_url)
                
                if redirections.get("ok"):
                    return await instance.recheck_url(url, redirections["url"])
                
                return redirections

            # 2. Check path segments
            # JS: /\/(fr|france|french|francais|français|fr-fr|fr_fr)(\/|$)/i.test(path)
            if re.search(r"/(fr|france|french|francais|français|fr-fr|fr_fr)(/|$)", path, re.IGNORECASE):
                return {"ok": True, "method": "pattern_match_path"}
            
            # 3. Check query parameters
            # JS: checks lang, locale, language params
            lang_params = ["lang", "locale", "language"]
            from urllib.parse import parse_qs
            q_params = parse_qs(query)
            
            for param in lang_params:
                val_list = q_params.get(param)
                if val_list:
                    val = val_list[0]
                    # JS: /^(fr|france|french|francais|français)(-[A-Z]{2})?$/i
                    if re.match(r"^(fr|france|french|francais|français)(-[A-Z]{2})?$", val, re.IGNORECASE):
                        return {"ok": True, "method": "pattern_match_query"}

            return False

        except Exception as e:
            return {"ok": False, "method": "invalid_url", "error": str(e)}

    async def recheck_url(self, original_url: str, new_url: str) -> Dict[str, Any]:
        """
        Called after redirection to verify if the new URL is valid.
        """
        if original_url == new_url:
            return {"ok": True, "method": "no_redirect", "url": original_url}

        # Recursive check on new URL (disable track_redirect to avoid loops)
        recheck = await DomainFR.check_url(new_url, track_redirect=False)
        recheck["original_url"] = original_url
        recheck["url"] = new_url
        return recheck

    async def handle_redirections(
        self,
        url_to_track: str,
        url: Optional[str] = None,
        target_content_type: str = "",
        proxy_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Uses RedirectTracker to resolve URL chain.
        """
        if not url: url = url_to_track

        try:
            self.tracker.redirects = []
            self.tracker.final_url = None

            # 1. Local check
            response = await self.tracker.get_url_redirection(url_to_track, proxy_url)
            content_type = response.get("content_type")

            if response.get("success") and response.get("status_code") == 200:
                result = {"ok": True, "url": response.get("final_url")}
                
                if target_content_type:
                    if content_type and target_content_type in content_type:
                        return result
                    # Content type doesn't match - fall through to raise exception (matches TypeScript)
                else:
                    return result
            
            # Fallback needed - raise exception to trigger Pemavor fallback
            raise Exception(json.dumps({
                "ok": False,
                "method": "redirect_failed",
                "url": url,
                "response": response,
            }))

        except Exception as e:
            logger.error(f"Error redirecting with httpx for {url}: {e}")
            
            # 2. Pemavor Fallback
            try:
                response = await RedirectTracker.get_url_redirection_pemavor([url_to_track])
                if response.get("success") and "data" in response:
                    datas = response["data"]["Data"]
                    
                    # datas is dict: {"url": [...chain...]}
                    for key, chain in datas.items():
                        # Chain is a list of objects
                        if not chain: continue
                        value = chain[-1] # Final hop
                        content_type = value.get("headers", {}).get("Content-Type")
                        status_code = value.get("status_code")
                        final_url = value.get("url")

                        if status_code == 200:
                            if target_content_type:
                                if content_type and target_content_type in content_type:
                                    return {"ok": True, "url": final_url}
                                else:
                                    return {
                                        "ok": False, 
                                        "url": final_url, 
                                        "status_code": status_code,
                                        "content_type": content_type
                                    }
                            else:
                                return {"ok": True, "url": final_url}
                        else:
                            return {"ok": False, "url": final_url, "status_code": status_code}
            
            except Exception as pemavor_error:
                logger.error(f"Error redirecting with Pemavor for {url}: {pemavor_error}")

            return {
                "ok": False,
                "method": "all_redirections_failed",
                "url": url
            }

    def _build_result(self, url: str, method: str, is_french: bool) -> Dict[str, Any]:
        return {
            "url": url,
            "method": method,
            "ok": is_french
        }

    async def check_page_if_french(self, content: str, is_check_url: bool = True) -> Dict[str, Any]:
        """
        Main entry point to verify if the loaded page is French.
        """
        url = self._homepage
        if not url or not content:
            return self._build_result(url, "Info_vide", False)

        # 1. Check URL patterns if requested
        if is_check_url:
            check_url_res = await DomainFR.check_url(url, track_redirect=False)
            if check_url_res.get("ok"):
                return self._build_result(url, "checkUrl", True)

        # 2. Check Forced Method (if we learned it from homepage previously)
        if self._forced_method:
            language = self.detect_language(content)
            if language and language["method"] == self._forced_method and language["value"] == "fr":
                return self._build_result(url, self._forced_method, True)
            
            return self._build_result(url, "Check_nok_forced", False)

        # 3. Check Content Auto-detection
        language = self.detect_language(content)
        
        if not language:
            return self._build_result(url, "Check_nok_v1", False)

        if language and language.get("method") and language.get("value") == "fr":
            return self._build_result(url, language["method"], True)

        return self._build_result(url, "Check_nok_v2", False)