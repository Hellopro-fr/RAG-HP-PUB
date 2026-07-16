import re
import logging
from difflib import SequenceMatcher
from bs4 import BeautifulSoup, Comment, Tag

logger = logging.getLogger(__name__)

class HeaderFooterExtractor:
    """
    A class to extract header and footer text from HTML content.
    It uses BeautifulSoup to parse the HTML and extract relevant text.
    """

    # Robust regex patterns based on real-world examples (GDPR, TCF, CMP banners)
    COOKIE_PATTERNS = [
        re.compile(r"(?:panneau de gestion|paramétrage|gérer le consentement) (?:des|aux) cookies", re.IGNORECASE),
        re.compile(r"(?:we use|nous utilisons) (?:des )?cookies", re.IGNORECASE),
        re.compile(r"(?:ce|this) (?:site|website) (?:utilise|uses) (?:des )?cookies", re.IGNORECASE),
        re.compile(r"(?:en poursuivant|by continuing) (?:votre|your) (?:navigation|browsing).*?(?:acceptez|accept)", re.IGNORECASE),
        re.compile(r"stocker et/ou accéder aux informations des appareils", re.IGNORECASE),
        re.compile(r"store,? access,? and process personal data", re.IGNORECASE),
        re.compile(r"(?:tout|all) (?:accepter|accept).*?(?:tout|all) (?:refuser|reject)", re.IGNORECASE),
        re.compile(r"continue without agreeing", re.IGNORECASE),
        re.compile(r"your privacy is our priority", re.IGNORECASE),
        re.compile(r"nous respectons votre vie privée", re.IGNORECASE),
        re.compile(r"cookies.*?(?:necessary|nécessaires).*?(?:functioning|bon fonctionnement)", re.IGNORECASE)
    ]

    def __init__(self, html_content: str):
        self.raw_html = html_content # Store raw HTML for boilerpy3 fallback
        try:
            self.soup = BeautifulSoup(html_content, 'html.parser')
            
            for element_to_remove in self.soup(["script", "style", "noscript", "iframe", "button", "form", "input", "textarea", "select", "option", "svg", "img"]):
                element_to_remove.decompose()
            for comment in self.soup.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse HTML: {e}", exc_info=True)
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

    # --- STRATEGY HELPERS ---

    def _get_signature_class(self, el: Tag) -> str:
        """Original signature strategy: Tag + Sorted Class Names."""
        classes = el.get('class', [])
        class_str = ".".join(sorted(classes)) if isinstance(classes, list) else classes
        return f"{el.name}.{class_str}" if class_str else el.name

    def _get_signature_structural(self, el: Tag) -> str:
        """
        ZONE A Improvement: Structural signature based on DOM path.
        Example: body > div:nth-of-type(1) > header:nth-of-type(1)
        """
        path = []
        
        # Get path segment for the element itself
        path.append(self._get_element_path_segment(el))
        
        # Traverse up parents to build full path
        for parent in el.parents:
            if parent.name == '[document]':
                break
            path.append(self._get_element_path_segment(parent))
            
        # Reverse to get root -> element order
        return " > ".join(reversed(path))

    def _get_element_path_segment(self, el: Tag) -> str:
        """Helper to get 'tag:nth-of-type(i)' string."""
        if not el.name: return "unknown"
        # Find previous siblings with the same tag name to determine index
        siblings = el.find_previous_siblings(el.name)
        index = len(siblings) + 1
        return f"{el.name}:nth-of-type({index})"

    def _build_structural_sig_map(self, root) -> dict:
        """O(N) batch equivalent of calling _get_signature_structural on every
        descendant Tag. One pre-order DFS: each parent keeps a running per-tag-name
        counter, so a child's nth-of-type index is assigned in O(1) instead of the
        O(position) find_previous_siblings(name) scan that made the per-element path
        O(N^2) over a large/repetitive DOM. Returns {id(el): "tag:nth-of-type(i) > ..."},
        byte-identical to _get_signature_structural(el) for every Tag.

        Valid only for the tree as it stands at call time (rebuild after any decompose);
        used for the read-only intersection scan (steps 3-4). The few post-purge re-signs
        (step 9) keep calling _get_signature_structural on the mutated tree."""
        sig_map = {}

        def walk(node, prefix):
            counts = {}  # per-parent same-tag-name running index
            for child in node.children:
                if not isinstance(child, Tag):
                    continue
                counts[child.name] = counts.get(child.name, 0) + 1
                segment = f"{child.name}:nth-of-type({counts[child.name]})"
                path = f"{prefix} > {segment}" if prefix else segment
                sig_map[id(child)] = path
                walk(child, path)

        walk(root, "")
        return sig_map

    def _is_cookie_banner(self, text: str) -> bool:
        """
        Detects if a text block is likely a cookie/consent banner using robust regex patterns.
        """
        if not text or len(text) > 3000: # Increase limit to catch large banners
            return False
            
        # Check against robust regex patterns
        for pattern in self.COOKIE_PATTERNS:
            if pattern.search(text):
                return True
            
        return False

    def run_intersection_logic(self, reference_htmls: list[str], strategy: str = "class", gap_config: dict = None) -> tuple[str, str, list[dict], dict, list[dict]]:
        """
        Uses boilerpy3 to strip noisy elements, then performs a structural tree 
        intersection using the specified signature strategy.
        
        Args:
            gap_config: Optional dictionary with weights for gap scoring.
                        Keys: 'text', 'article', 'h1', 'h2'.
        """
        cleaned_htmls = {"main": "", "refs": []}
        gap_details = []
        
        # Default Weights
        if not gap_config:
            gap_config = {
                'text': 1.0,
                'article': 10000.0,
                'h1': 5000.0,
                'h2': 1000.0
            }
        
        if not hasattr(self, 'raw_html') or not self.raw_html or not reference_htmls:
            return "", "", [], cleaned_htmls, gap_details
        
        try:
            from boilerpy3 import extractors as BoilerpyExtractor
        except ImportError:
            logging.error("boilerpy3 not installed.")
            return "", "", [], cleaned_htmls, gap_details

        try:
            extractor = BoilerpyExtractor.KeepEverythingExtractor()
            
            # 1. Clean the Main HTML
            clean_main_html = extractor.get_marked_html(self.raw_html)
            if not clean_main_html: return "", "", [], cleaned_htmls, gap_details
            cleaned_htmls["main"] = clean_main_html
            main_soup = BeautifulSoup(clean_main_html, 'html.parser')
            
            # 2. Clean the Reference HTMLs
            clean_refs = []
            for ref_html in reference_htmls:
                c_ref = extractor.get_marked_html(ref_html)
                if c_ref:
                    cleaned_htmls["refs"].append(c_ref)
                    clean_refs.append(BeautifulSoup(c_ref, 'html.parser'))
            if not clean_refs: return "", "", [], cleaned_htmls, gap_details
        except Exception as e:
            logging.error(f"Error during boilerpy3 cleaning: {e}")
            return "", "", [], cleaned_htmls, gap_details

        # 3. Build Reference Maps (Signature -> Text Content)
        # Allows us to retrieve the actual text content from reference pages for visualization
        ref_maps = []

        # Decide which signature function to use
        get_sig = self._get_signature_structural if strategy == "structural" else self._get_signature_class
        
        # Expanded target tags to support Tables, Semantic5, and Definition Lists
        target_tags = ['div', 'header', 'footer', 'nav', 'ul', 'ol', 'dl', 'dt', 'dd', 'section', 'aside', 'main', 'article', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'td']

        for ref_soup in clean_refs:
            struct_map = self._build_structural_sig_map(ref_soup) if strategy == "structural" else None
            sig_map = {}
            for el in ref_soup.find_all(target_tags):
                if strategy == "class" and not el.get('class') and el.name not in ['header', 'footer', 'nav', 'main', 'article']:
                    continue
                s = struct_map[id(el)] if struct_map is not None else get_sig(el)
                # Store the text. If multiple elements have the same signature, we store the first one found.
                # In most boilerplate scenarios, structural signatures are unique enough or repetition is acceptable.
                if s not in sig_map:
                    sig_map[s] = self.get_cleaned_text(el)
            ref_maps.append(sig_map)

        # 4. Find matching nodes in the Main HTML (The Intersection)
        potential_candidates = []
        all_main_elements = main_soup.find_all(target_tags)
        main_struct_map = self._build_structural_sig_map(main_soup) if strategy == "structural" else None

        for index, el in enumerate(all_main_elements):
            sig = main_struct_map[id(el)] if main_struct_map is not None else get_sig(el)

            if strategy == "class" and not el.get('class') and el.name not in ['header', 'footer', 'nav', 'main', 'article']:
                continue
            
            # Intersection Check & Content Similarity
            if all(sig in r_map for r_map in ref_maps):
                potential_candidates.append((index, el, sig))

        # 4.5. Cookie Purge (DESTRUCTIVE PASS on potential candidates)
        # We perform this BEFORE building the final candidates list to ensure
        # that parent elements have their text updated (removed cookies)
        for index, el, sig in potential_candidates:
            # We must re-get the text because previous decompositions might have altered it
            if el.parent is None: continue 

            current_text = self.get_cleaned_text(el)
            # Use the robust regex-based check
            if self._is_cookie_banner(current_text):
                logging.info(f"Removing cookie banner element during intersection: {current_text[:50]}...")
                el.decompose() 

        # 5. Build Final Candidates with REFRESHED Text
        candidates = []
        detailed_intersections = []
        
        # Re-iterate through potential candidates
        for index, el, sig in potential_candidates:
            if el.parent is None:
                continue # Element was decomposed
            
            # Get FRESH text (post-purge)
            text_main = self.get_cleaned_text(el)
            ref_texts = [r_map.get(sig, "") for r_map in ref_maps]
            
            # Re-apply Content Similarity Check on the FRESH text
            is_content_similar = True
            if text_main and len(text_main) > 10: # Only check similarity for significant blocks
                for r_text in ref_texts:
                    if not r_text: 
                        is_content_similar = False
                        break
                    ratio = SequenceMatcher(None, text_main, r_text).ratio()
                    if ratio < 1: # Strict exact match for stability testing
                        is_content_similar = False
                        break
            
            if is_content_similar and (len(text_main.split()) >= 2 or "©" in text_main):
                match_detail = {
                    "signature": sig,
                    "text_main": text_main,
                    "text_ref1": ref_texts[0] if len(ref_texts) > 0 else "",
                    "text_ref2": ref_texts[1] if len(ref_texts) > 1 else "",
                    "status": "Pending" # Default status
                }
                candidates.append((index, el, text_main, len(text_main.split()), match_detail))

        # 6. Filter nested candidates (keep highest level)
        top_level_candidates = []
        for i, (idx, el, text, word_count, detail) in enumerate(candidates):
            is_child = any(parent in [c[1] for c in candidates] for parent in el.parents)
            if not is_child:
                top_level_candidates.append((idx, el, text, word_count))
                detailed_intersections.append(detail)

        if not top_level_candidates:
            return "", "", [], cleaned_htmls, gap_details

        # 7. Identify Main Content Pivot using Weighted Largest Gap
        candidate_indices = sorted([t[0] for t in top_level_candidates])
        boundary_indices = [-1] + candidate_indices + [len(all_main_elements)]
        
        max_gap_score = -1
        header_cutoff_index = -1 
        footer_start_index = len(all_main_elements)
        
        for i in range(len(boundary_indices) - 1):
            start_idx = boundary_indices[i] + 1
            end_idx = boundary_indices[i+1]
            gap_score = 0.0
            
            # Metadata for visualization
            gap_meta = {
                "start_index": start_idx,
                "end_index": end_idx,
                "score": 0.0,
                "text_score": 0.0,
                "tag_bonus": 0.0
            }
            
            for gap_el_idx in range(start_idx, end_idx):
                if gap_el_idx >= len(all_main_elements): break
                el = all_main_elements[gap_el_idx]
                if el.parent is None: continue
                
                text_len = len(self.get_cleaned_text(el).split())
                
                # Apply weights from config
                score_increment = text_len * gap_config.get('text', 1.0)
                gap_score += score_increment
                gap_meta["text_score"] += score_increment
                
                bonus = 0.0
                if el.name in ['main', 'article']: 
                    bonus = gap_config.get('article', 10000.0)
                if el.find('h1'): 
                    bonus = max(bonus, gap_config.get('h1', 5000.0))
                if el.find('h2'): 
                    bonus = max(bonus, gap_config.get('h2', 1000.0))
                
                gap_score += bonus
                gap_meta["tag_bonus"] += bonus
            
            gap_meta["score"] = gap_score
            gap_details.append(gap_meta)
            
            if gap_score > max_gap_score:
                max_gap_score = gap_score
                header_cutoff_index = boundary_indices[i]
                footer_start_index = boundary_indices[i+1]

        # Mark winner in gap details
        for gd in gap_details:
            gd["is_winner"] = (gd["score"] == max_gap_score)

        # 8. Cluster Filtering
        final_header_indices = []
        final_footer_indices = []
        
        for t in top_level_candidates:
            idx = t[0]
            if idx <= header_cutoff_index:
                final_header_indices.append(idx)
            elif idx >= footer_start_index:
                final_footer_indices.append(idx)

        # 9. Assembly with Deduplication and Status Tracking
        header_texts = []
        footer_texts = []
        seen_blocks = set()

        for k, (idx, el, text, wc) in enumerate(top_level_candidates):
            detail = detailed_intersections[k]
            current_text = self.get_cleaned_text(el)
            if not current_text: 
                detail['status'] = "Dropped (Empty)"
                continue

            sig = get_sig(el)
            key = (sig, current_text)
            if key in seen_blocks:
                detail['status'] = "Dropped (Duplicate)"
                continue
            
            if idx in final_header_indices:
                header_texts.append(current_text)
                seen_blocks.add(key)
                detail['status'] = "Kept (Header)"
            elif idx in final_footer_indices:
                footer_texts.append(current_text)
                seen_blocks.add(key)
                detail['status'] = "Kept (Footer)"
            else:
                detail['status'] = "Dropped (Middle Island)"

        header_result = " ".join(header_texts).strip()
        footer_result = " ".join(footer_texts).strip()

        if len(header_result) > 10000: header_result = header_result[:10000]
        if len(footer_result) > 10000: footer_result = footer_result[:10000]

        return header_result, footer_result, detailed_intersections, cleaned_htmls, gap_details

    def extract_with_fallback(self, reference_htmls: list[str]) -> dict:
        """Production Logic: Structural -> Class -> Original"""
        if not self.soup:
            return {"header": "", "header_method": "None", "footer": "", "footer_method": "None"}

        # Order: 1. Structural, 2. Class, 3. Original
        
        # 1. Structural Strategy
        fallback_h, fallback_f, _, _, _ = self.run_intersection_logic(reference_htmls, strategy="structural")
        
        if fallback_h and fallback_f:
            return {
                "header": fallback_h, "header_method": "Fallback (boilerpy3 Structural Intersection)",
                "footer": fallback_f, "footer_method": "Fallback (boilerpy3 Structural Intersection)"
            }
            
        # 2. Class Strategy
        fallback_h_class, fallback_f_class, _, _, _ = self.run_intersection_logic(reference_htmls, strategy="class")
        
        # Partial Merge or Fallback
        header = fallback_h if fallback_h else fallback_h_class
        footer = fallback_f if fallback_f else fallback_f_class
        
        header_method = "Fallback (Structural)" if fallback_h else ("Fallback (Class)" if fallback_h_class else "None")
        footer_method = "Fallback (Structural)" if fallback_f else ("Fallback (Class)" if fallback_f_class else "None")

        # 3. Original Method (Last Resort if completely empty)
        if not header:
            header = self.extract_header(self.soup)
            if header: header_method = "Original (Semantic/CSS Pattern)"
            
        if not footer:
            footer = self.extract_footer(self.soup)
            if footer: footer_method = "Original (Semantic/CSS Pattern)"

        return {
            "header": header,
            "header_method": header_method,
            "footer": footer,
            "footer_method": footer_method
        }

    def extract_all_debug(self, reference_htmls: list[str], gap_config: dict = None) -> dict:
        """Debug Logic"""
        if not self.soup: return {}

        old_header = self.extract_header(self.soup)
        old_footer = self.extract_footer(self.soup)

        # Pass gap_config to intersection logic
        class_h, class_f, class_details, cleaned_htmls, gap_analysis = self.run_intersection_logic(
            reference_htmls, strategy="class", gap_config=gap_config
        )
        
        struct_h, struct_f, struct_details, _, _ = self.run_intersection_logic(
            reference_htmls, strategy="structural", gap_config=gap_config
        )

        if old_header:
            selected_header = old_header
            header_method_used = "Original (Semantic/CSS Pattern)"
        elif class_h:
            selected_header = class_h
            header_method_used = "Fallback (boilerpy3 Class Intersection)"
        elif struct_h:
             selected_header = struct_h
             header_method_used = "Fallback (boilerpy3 Structural Intersection)"
        else:
            selected_header = ""
            header_method_used = "None"

        if old_footer:
            selected_footer = old_footer
            footer_method_used = "Original (Semantic/CSS Pattern)"
        elif class_f:
            selected_footer = class_f
            footer_method_used = "Fallback (boilerpy3 Class Intersection)"
        elif struct_f:
            selected_footer = struct_f
            footer_method_used = "Fallback (boilerpy3 Structural Intersection)"
        else:
            selected_footer = ""
            footer_method_used = "None"

        return {
            "header_old": old_header,
            "header_class": class_h,
            "header_structural": struct_h,
            "header_selected": selected_header,
            "header_method_used": header_method_used,
            
            "footer_old": old_footer,
            "footer_class": class_f,
            "footer_structural": struct_f,
            "footer_selected": selected_footer,
            "footer_method_used": footer_method_used,

            "intersections_class": class_details,
            "intersections_structural": struct_details,
            
            "cleaned_html_main": cleaned_htmls.get("main", ""),
            "cleaned_html_ref1": cleaned_htmls.get("refs", ["", ""])[0] if len(cleaned_htmls.get("refs", [])) > 0 else "",
            "cleaned_html_ref2": cleaned_htmls.get("refs", ["", ""])[1] if len(cleaned_htmls.get("refs", [])) > 1 else "",
            
            "gap_analysis": gap_analysis
        }