import re

from bs4 import BeautifulSoup, Comment

class HeaderFooterExtractor:
    """
    A class to extract header and footer text from HTML content.
    It uses BeautifulSoup to parse the HTML and extract relevant text.
    """

    def __init__(self, html_content: str):
        try:
            self.soup = BeautifulSoup(html_content, 'html.parser')
            
            for element_to_remove in self.soup(["script", "style", "noscript", "iframe", "button", "form", "input", "textarea", "select", "option", "svg", "img"]):
                element_to_remove.decompose()
            for comment in self.soup.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()
        except Exception as e:
            print(f"Erreur lors de l'analyse HTML: {e}")
            self.soup = None
            return
        
    # This is a helper function used by the main extraction functions.
    # Its purpose is to get clean, readable text from an HTML element.
    def get_cleaned_text(self, element, max_length=None):
        """
        Extracts and cleans the text from a BeautifulSoup element.
        It removes scripts, styles, comments, and extra whitespace.
        """
        if not element:
            return ""
        
        texts = []
        # Find all text nodes within the element.
        for elem in element.find_all(string=True):
            # Ignore text that is actually an HTML comment.
            if isinstance(elem, Comment): 
                continue
            # Ignore text found inside tags that are not visible content (like script or style tags).
            if elem.parent.name in ['script', 'style', 'head', 'title', 'meta', '[document]']: 
                continue
            # Strip leading/trailing whitespace from the text.
            text = elem.strip()
            # Only add non-empty text strings.
            if text:
                texts.append(text)
        
        # Join all the collected text parts with a single space.
        full_text = " ".join(texts)
        # Replace multiple whitespace characters (spaces, tabs, newlines) with a single space.
        full_text = re.sub(r'\s+', ' ', full_text).strip() 

        # This part is currently not used (pass), but could be used to truncate text if needed.
        if max_length and len(full_text) > max_length:
            pass 
        return full_text
    
    def extract_header(self, soup: BeautifulSoup) -> str:
        """
        Analyzes a BeautifulSoup object to robustly find and extract the text content of the main site header.

        It works by collecting all possible "candidate" elements using various techniques,
        assigning a priority to each based on the reliability of the detection method,
        and then selecting the best candidate after filtering out unsuitable ones.

        Args:
            soup (BeautifulSoup): The parsed HTML of the page.

        Returns:
            str: The cleaned text content of the identified header, or an empty string if none is found.
        """
        # This list will store all potential header elements found.
        # Each item will be a dictionary containing the element, its priority, and the method used to find it.
        candidates = []
        
        # --- METHOD 1: SEMANTIC HTML (<header> tag) ---
        # This is the most reliable method, as the <header> tag is specifically for this purpose.
        semantic_header = soup.find('header')
        if semantic_header:
            # Priority 1 (Highest): A <nav> element inside a <header> is the strongest indicator of a main navigation menu.
            nav_in_header = semantic_header.find('nav')
            if nav_in_header:
                candidates.append({"element": nav_in_header, "priority": 1, "method": "semantic_header_nav"})
            
            # Priority 1.5: Look for common container divs/sections inside the <header> with class names like "nav" or "menu".
            common_header_containers = semantic_header.select(
                'div[class*="nav"], div[class*="menu"], div[id*="nav"], div[id*="menu"], section[class*="nav"], section[class*="menu"]'
            )
            if common_header_containers:
                for chc in common_header_containers:
                    # Add this candidate, ensuring it's not a parent of the already-found <nav> element.
                    if not nav_in_header or (nav_in_header and chc in nav_in_header.find_parents()):
                        candidates.append({"element": chc, "priority": 1.5, "method": "semantic_header_container"})
            
            # Priority 2: If no specific container is found inside, the entire <header> element is a good candidate.
            candidates.append({"element": semantic_header, "priority": 2, "method": "semantic_header_full"})

        # --- METHOD 2: ARIA ROLES (Accessibility) ---
        # The `role="banner"` is the accessibility standard for identifying the site header. Very reliable.
        aria_banner = soup.find(attrs={"role": re.compile(r"\bbanner\b", re.I)})
        if aria_banner:
            candidates.append({"element": aria_banner, "priority": 3, "method": "aria_banner"})

        # --- METHOD 3: PATTERN MATCHING on IDs and CLASSes ---
        # This is the "robust" part, for sites that don't use modern semantic HTML.
        # It searches for common naming conventions used by developers.
        header_patterns = [
            re.compile(r"^(main|site|top|global)-?header(-?(wrapper|container|inner|bar|nav))?$", re.I),
            re.compile(r"^masthead$", re.I), re.compile(r"^top(-?nav)?(-?bar)?$", re.I),
            re.compile(r"^(main|site|primary)-?nav(igation)?(-?(bar|menu|wrapper))?$", re.I),
            re.compile(r"\b(main|site|top|global)-?header(-?(wrapper|container|inner|bar|content|style|area))?\b", re.I),
            re.compile(r"\b(main|primary|top)-?nav(igation)?(-?(bar|menu|wrapper|container))?\b", re.I),
            re.compile(r"\b(menu|nav)-?principal(e)?\b", re.I), re.compile(r"\bheader-?main\b", re.I),
            re.compile(r"\bheader__container--main-header\b", re.I), re.compile(r"\bheader-?content\b", re.I)
        ]
        # We check common container tags like 'div', 'nav', and 'section'. We limit the search to the top of the page.
        for tag_name in ['div', 'nav', 'section']:
            for el in soup.find_all(tag_name, limit=20):
                # CRUCIAL CHECK: Ensure the element is not part of the main page content.
                # This prevents finding an <article>'s header instead of the site's header.
                in_main_content = False
                for parent in el.parents:
                    if parent.name in ['main', 'article', 'aside'] or \
                    (parent.get('id') and any(kw in parent['id'].lower() for kw in ['content', 'main', 'primary', 'page'])) or \
                    (parent.get('class') and any(kw in c.lower() for kw in ['content', 'main', 'primary', 'page', 'post'] for c in parent['class'])):
                        in_main_content = True; break
                if in_main_content: continue # If it's in the main content, skip it.
                
                found_by_pattern = False
                # Priority 4: Matching an ID is more specific and reliable than a class.
                if el.get('id'):
                    for pattern in header_patterns:
                        if pattern.search(el['id']):
                            candidates.append({"element": el, "priority": 4, "method": f"id_pattern:{pattern.pattern}"}); found_by_pattern = True; break
                if found_by_pattern: continue
                # Priority 4.5: Matching a class name is also a good signal.
                if el.get('class'):
                    class_string = " ".join(el['class'])
                    for pattern in header_patterns:
                        if pattern.search(class_string):
                            candidates.append({"element": el, "priority": 4.5, "method": f"class_pattern:{pattern.pattern}"}); found_by_pattern = True; break
                if found_by_pattern: continue
        
        # --- FINAL SELECTION PROCESS ---
        unique_candidates = []
        seen_elements = set()
        
        # Sort all found candidates by their priority (lower number is better).
        for cand in sorted(candidates, key=lambda x: x['priority']):
            # Ensure we only process each unique element once, even if found by multiple methods.
            if cand["element"] not in seen_elements:
                text_content = self.get_cleaned_text(cand["element"])
                # Sanity Check: A valid header must have some text, but not be excessively large (e.g., half the page).
                if text_content and 10 < len(text_content) < (len(self.get_cleaned_text(soup.body)) * 0.5 if soup.body else 5000):
                    unique_candidates.append(cand)
                    seen_elements.add(cand["element"])

        # If we have at least one valid candidate, the best one is the first in the sorted list.
        if unique_candidates:
            header_el = unique_candidates[0]["element"]
            # print(f"Selected Header ({unique_candidates[0]['method']}): {get_cleaned_text(header_el)[:100]}...") # Optional: for debugging
            return self.get_cleaned_text(header_el)
        
        # If no suitable header was found after all checks, return an empty string.
        # print("No suitable header found.") # Optional: for debugging
        return ""
    
    def extract_footer(self, soup: BeautifulSoup) -> str:
        """
        Analyzes a BeautifulSoup object to robustly find and extract the text content of the main site footer.

        It follows the same "candidate-gathering" philosophy as the header extraction but uses
        footer-specific logic, such as searching from the bottom of the page up and looking for
        footer-specific keywords (e.g., 'copyright', 'privacy').

        Args:
            soup (BeautifulSoup): The parsed HTML of the page.

        Returns:
            str: The cleaned text content of the identified footer, or an empty string if none is found.
        """
        # This list will store all potential footer elements found.
        candidates = []
        
        # --- METHOD 1: SEMANTIC HTML (<footer> tag) ---
        # The <footer> tag is the correct semantic element for a site footer.
        semantic_footer = soup.find('footer')
        if semantic_footer:
            # Priority 1 (Highest): Look for common content wrappers inside the <footer> tag first.
            common_footer_containers = semantic_footer.select(
                'div[class*="content"], div[class*="container"], div[class*="wrapper"], div[id*="content"], section[class*="content"]'
            )
            if common_footer_containers:
                for cfc in common_footer_containers:
                    candidates.append({"element": cfc, "priority": 1, "method": "semantic_footer_container"})
            
            # Priority 1.5: The entire <footer> element is the next best choice.
            candidates.append({"element": semantic_footer, "priority": 1.5, "method": "semantic_footer_full"})

        # --- METHOD 2: ARIA ROLES (Accessibility) ---
        # The `role="contentinfo"` is the accessibility standard for the footer, containing metadata about the site.
        aria_contentinfo = soup.find(attrs={"role": re.compile(r"\bcontentinfo\b", re.I)})
        if aria_contentinfo:
            candidates.append({"element": aria_contentinfo, "priority": 2, "method": "aria_contentinfo"})

        # --- METHOD 3: PATTERN MATCHING (Footer-Specific) ---
        # Defines a list of regular expressions to find common footer naming conventions.
        footer_patterns = [
            re.compile(r"^(main|site|global|page)-?footer(-?(wrapper|container|inner|bottom|colophon|content|widgets|nav|navigation))?$", re.I),
            re.compile(r"^colophon$", re.I), re.compile(r"^(page|site)-?bottom(-?bar)?$", re.I),
            re.compile(r"^site-?info(rmation)?$", re.I),
            re.compile(r"\b(main|site|global|page)-?footer(-?(wrapper|container|inner|bottom|content|area|style|widgets|text|info|nav|navigation))?\b", re.I),
            re.compile(r"\bcolophon(-?wrapper)?\b", re.I), re.compile(r"\b(site-)?info(rmation)?\b", re.I),
            re.compile(r"\bcopyright(-?area|-?wrapper)?\b", re.I), re.compile(r"\blegal\b", re.I),
            re.compile(r"\bfooter__content\b", re.I), re.compile(r"\bfooter-?widgets\b", re.I),
            re.compile(r"\bfooter-?nav\b", re.I), re.compile(r"\bfooter-?bottom\b", re.I)
        ]
        
        # KEY STRATEGY FOR FOOTERS: Search from the bottom of the page upwards.
        # We collect the last 50 relevant tags to check, as footers are at the end of the document.
        possible_footer_tags = []
        if soup.body:
            all_relevant_tags = soup.body.find_all(['div', 'section', 'footer'], recursive=True)
            # We iterate through the list of the last elements in reverse order.
            for el in reversed(all_relevant_tags[-50:]):
                possible_footer_tags.append(el)

        for el in possible_footer_tags: 
            # We are less strict here than for the header, but we still want to avoid
            # footers belonging to a specific article or post.
            in_main_content = False
            for parent in el.parents:
                if parent.name in ['article'] or \
                (parent.get('class') and any(kw in c.lower() for kw in ['article-content', 'post-content'] for c in parent['class'])):
                    in_main_content = True; break
            if in_main_content: continue
            
            found_by_pattern = False
            # Priority 3: Matching an ID is a strong signal.
            if el.get('id'):
                for pattern in footer_patterns:
                    if pattern.search(el['id']):
                        candidates.append({"element": el, "priority": 3, "method": f"id_pattern:{pattern.pattern}"}); found_by_pattern = True; break
            if found_by_pattern: continue
            # Priority 3.5: Matching a class is also a good signal.
            if el.get('class'):
                class_string = " ".join(el['class'])
                for pattern in footer_patterns:
                    if pattern.search(class_string):
                        candidates.append({"element": el, "priority": 3.5, "method": f"class_pattern:{pattern.pattern}"}); found_by_pattern = True; break
            if found_by_pattern: continue
        
        # --- FINAL SELECTION PROCESS (with advanced footer-specific filtering) ---
        unique_candidates = []
        seen_elements = set()
        for cand in sorted(candidates, key=lambda x: x['priority']):
            if cand["element"] not in seen_elements:
                text_content = self.get_cleaned_text(cand["element"])
                
                # ADVANCED FILTER 1: Check for common footer keywords. This is a very strong indicator.
                has_footer_keywords = any(kw in text_content.lower() for kw in ['copyright', '©', 'privacy', 'terms', 'contact', 'rights reserved', 'mentions légales', 'données personnelles', 'adresse', 'téléphone', 'newsletter', 'suivez-nous', 'follow us'])
                
                # ADVANCED FILTER 2: Count the number of links. Footers are usually link-heavy.
                link_count = len(cand["element"].find_all('a', recursive=False))
                
                # FINAL VALIDATION: A candidate is valid if it has a reasonable text length AND
                # it either contains footer keywords OR it has links.
                if text_content and 5 < len(text_content) < (len(self.get_cleaned_text(soup.body)) * 0.5 if soup.body else 5000) and (has_footer_keywords or link_count > 0):
                    unique_candidates.append(cand)
                    seen_elements.add(cand["element"])
        
        # If we have valid candidates, the best one is the first in our sorted list.
        if unique_candidates:
            footer_el = unique_candidates[0]["element"]
            # print(f"Selected Footer ({unique_candidates[0]['method']}): {get_cleaned_text(footer_el)[:100]}...") # Optional: for debugging
            return self.get_cleaned_text(footer_el)
            
        # If no suitable footer was found, return an empty string.
        # print("No suitable footer found.") # Optional: for debugging
        return ""