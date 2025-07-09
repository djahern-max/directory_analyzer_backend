import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("app.utils.text_utils")


def clean_text(text: str) -> str:
   """
   Clean text by removing extra whitespace and normalizing
   
   Args:
       text: Input text
       
   Returns:
       Cleaned text
   """
   if not text:
       return ""
   
   # Remove extra whitespace
   cleaned = re.sub(r'\s+', ' ', text.strip())
   
   # Remove null bytes
   cleaned = cleaned.replace('\x00', '')
   
   return cleaned


def extract_dollar_amounts(text: str) -> List[Dict[str, Any]]:
   """
   Extract dollar amounts from text
   
   Args:
       text: Input text
       
   Returns:
       List of dictionaries with amount information
   """
   amounts = []
   
   # Pattern for dollar amounts with various formats
   patterns = [
       r'\$\s*([\d,]+\.?\d*)',  # $1,000.00 or $1000
       r'([\d,]+\.?\d*)\s*dollars?',  # 1000 dollars
       r'USD\s*([\d,]+\.?\d*)',  # USD 1000
   ]
   
   for pattern in patterns:
       matches = re.finditer(pattern, text, re.IGNORECASE)
       for match in matches:
           amount_str = match.group(1)
           try:
               # Remove commas and convert to float
               amount_value = float(amount_str.replace(',', ''))
               amounts.append({
                   "text": match.group(0),
                   "value": amount_value,
                   "position": match.span()
               })
           except ValueError:
               continue
   
   return amounts


def extract_dates(text: str) -> List[Dict[str, Any]]:
   """
   Extract dates from text in various formats
   
   Args:
       text: Input text
       
   Returns:
       List of dictionaries with date information
   """
   dates = []
   
   # Common date patterns
   patterns = [
       r'\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b',  # MM/DD/YYYY or MM-DD-YYYY
       r'\b(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\b',  # YYYY/MM/DD or YYYY-MM-DD
       r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b',  # Month DD, YYYY
       r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b',  # DD Month YYYY
   ]
   
   for pattern in patterns:
       matches = re.finditer(pattern, text, re.IGNORECASE)
       for match in matches:
           dates.append({
               "text": match.group(0),
               "groups": match.groups(),
               "position": match.span()
           })
   
   return dates


def extract_company_names(text: str) -> List[str]:
   """
   Extract potential company names from text
   
   Args:
       text: Input text
       
   Returns:
       List of potential company names
   """
   companies = []
   
   # Patterns for company suffixes
   company_suffixes = [
       r'\b\w+\s+(LLC|Inc\.?|Corp\.?|Corporation|Company|Co\.?|Limited|Ltd\.?)\b',
       r'\b\w+\s+\w+\s+(LLC|Inc\.?|Corp\.?|Corporation|Company|Co\.?|Limited|Ltd\.?)\b',
       r'\b\w+\s+\w+\s+\w+\s+(LLC|Inc\.?|Corp\.?|Corporation|Company|Co\.?|Limited|Ltd\.?)\b'
   ]
   
   for pattern in company_suffixes:
       matches = re.finditer(pattern, text, re.IGNORECASE)
       for match in matches:
           company_name = match.group(0).strip()
           if company_name not in companies:
               companies.append(company_name)
   
   return companies


def extract_contract_numbers(text: str) -> List[str]:
   """
   Extract potential contract numbers from text
   
   Args:
       text: Input text
       
   Returns:
       List of potential contract numbers
   """
   contract_numbers = []
   
   # Patterns for contract numbers
   patterns = [
       r'\b(?:Contract|Agreement|Job|Project|CTDOT)\s*#?\s*([A-Z0-9\-]+)\b',
       r'\b([A-Z]{2,4}[\-\s]*\d{3,8})\b',  # State contract patterns
       r'\b(\d{4}[\-\s]*\d{2,4})\b',  # Year-based contract numbers
   ]
   
   for pattern in patterns:
       matches = re.finditer(pattern, text, re.IGNORECASE)
       for match in matches:
           contract_num = match.group(1).strip()
           if contract_num not in contract_numbers:
               contract_numbers.append(contract_num)
   
   return contract_numbers


def summarize_text(text: str, max_sentences: int = 3) -> str:
   """
   Create a simple summary of text by taking first few sentences
   
   Args:
       text: Input text
       max_sentences: Maximum number of sentences to include
       
   Returns:
       Text summary
   """
   if not text:
       return ""
   
   # Split into sentences (simple approach)
   sentences = re.split(r'[.!?]+', text)
   
   # Clean and filter sentences
   clean_sentences = []
   for sentence in sentences:
       sentence = sentence.strip()
       if len(sentence) > 20:  # Filter out very short fragments
           clean_sentences.append(sentence)
       if len(clean_sentences) >= max_sentences:
           break
   
   return '. '.join(clean_sentences) + '.' if clean_sentences else ""


def calculate_text_statistics(text: str) -> Dict[str, Any]:
   """
   Calculate basic statistics about text
   
   Args:
       text: Input text
       
   Returns:
       Dictionary with text statistics
   """
   if not text:
       return {
           "character_count": 0,
           "word_count": 0,
           "sentence_count": 0,
           "paragraph_count": 0,
           "average_word_length": 0,
           "average_sentence_length": 0
       }
   
   # Basic counts
   char_count = len(text)
   word_count = len(text.split())
   sentence_count = len(re.split(r'[.!?]+', text))
   paragraph_count = len([p for p in text.split('\n\n') if p.strip()])
   
   # Averages
   avg_word_length = sum(len(word) for word in text.split()) / word_count if word_count > 0 else 0
   avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
   
   return {
       "character_count": char_count,
       "word_count": word_count,
       "sentence_count": sentence_count,
       "paragraph_count": paragraph_count,
       "average_word_length": round(avg_word_length, 2),
       "average_sentence_length": round(avg_sentence_length, 2)
   }


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
   """
   Truncate text to maximum length with suffix
   
   Args:
       text: Input text
       max_length: Maximum length including suffix
       suffix: Suffix to add when truncating
       
   Returns:
       Truncated text
   """
   if not text or len(text) <= max_length:
       return text
   
   return text[:max_length - len(suffix)] + suffix


def normalize_whitespace(text: str) -> str:
   """
   Normalize whitespace in text
   
   Args:
       text: Input text
       
   Returns:
       Text with normalized whitespace
   """
   if not text:
       return ""
   
   # Replace multiple whitespace with single space
   normalized = re.sub(r'\s+', ' ', text)
   
   # Clean up line breaks
   normalized = re.sub(r'\n\s*\n', '\n\n', normalized)
   
   return normalized.strip()


def extract_keywords(text: str, min_length: int = 3, max_keywords: int = 20) -> List[str]:
   """
   Extract potential keywords from text
   
   Args:
       text: Input text
       min_length: Minimum keyword length
       max_keywords: Maximum number of keywords to return
       
   Returns:
       List of keywords
   """
   if not text:
       return []
   
   # Convert to lowercase and split into words
   words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
   
   # Filter by length and common stop words
   stop_words = {
       'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
       'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had',
       'will', 'would', 'could', 'should', 'may', 'might', 'can', 'shall',
       'this', 'that', 'these', 'those', 'a', 'an', 'as', 'if', 'when',
       'where', 'how', 'why', 'what', 'which', 'who', 'whom', 'whose'
   }
   
   keywords = []
   word_counts = {}
   
   for word in words:
       if (len(word) >= min_length and 
           word not in stop_words and 
           word.isalpha()):
           word_counts[word] = word_counts.get(word, 0) + 1
   
   # Sort by frequency and take top keywords
   sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
   keywords = [word for word, count in sorted_words[:max_keywords]]
   
   return keywords
