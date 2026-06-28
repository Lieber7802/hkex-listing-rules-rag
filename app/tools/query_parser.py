import re
from typing import List, Dict, Optional, Any, Tuple


class QueryParser:
    @staticmethod
    def extract_numbers(text: str) -> List[float]:
        """Extract all unique numbers, sorted ascending.

        For position-aware extraction, use extract_numbers_ordered().
        """
        if not text:
            return []
        # Pattern matches: decimals with thousands separators, decimals, integers with thousands separators, plain integers, scientific notation
        pattern = r'[+-]?(?:\d+(?:[,\s]\d{3})*\.\d+|\d+(?:[,\s]\d{3})*|\d+\.\d+|\d+)(?:[eE][+-]?\d+)?'
        matches = re.findall(pattern, text)
        numbers = []
        for match in matches:
            cleaned = match.replace(',', '').replace(' ', '')
            try:
                numbers.append(float(cleaned))
            except ValueError:
                continue
        return sorted(list(set(numbers)))

    @staticmethod
    def extract_numbers_ordered(text: str) -> List[Tuple[float, int]]:
        """Extract numbers with character positions, preserving document order."""
        if not text:
            return []
        pattern = r'[+-]?(?:\d+(?:[,\s]\d{3})*\.\d+|\d+(?:[,\s]\d{3})*|\d+\.\d+|\d+)(?:[eE][+-]?\d+)?'
        seen = set()
        results: List[Tuple[float, int]] = []
        for m in re.finditer(pattern, text):
            num_str = m.group(0)
            cleaned = num_str.replace(',', '').replace(' ', '')
            try:
                val = float(cleaned)
                if val not in seen:
                    seen.add(val)
                    results.append((val, m.start()))
            except ValueError:
                continue
        return results
    
    @staticmethod
    def extract_currency_values(text: str) -> Dict[str, Any]:
        if not text:
            return {}
        result = {"hk_dollars": [], "usd": [], "rmb": [], "raw_numbers": []}
        def apply_scale(amount: str, scale_str: str) -> float:
            try:
                val = float(amount.replace(',', '').replace(' ', ''))
                if 'bn' in scale_str.lower() or 'billion' in scale_str.lower():
                    val *= 1_000_000_000
                elif 'm' in scale_str.lower() or 'million' in scale_str.lower():
                    val *= 1_000_000
                elif 'k' in scale_str.lower() or 'thousand' in scale_str.lower():
                    val *= 1_000
                return val
            except:
                return 0
        hk_pattern = r'(?:HK\$|HKD)[\s]*(\d+(?:[.,]\d+)?)\s*(?:million|m|bn|billion|k|thousand)?|(\d+(?:[.,]\d+)?)\s*(?:million|m|bn|billion|k|thousand)?\s*(?:HK\$|HKD)'
        for match in re.finditer(hk_pattern, text, re.IGNORECASE):
            amount = match.group(1) or match.group(2)
            if amount:
                val = apply_scale(amount, match.group(0))
                if val > 0:
                    result["hk_dollars"].append(val)
        usd_pattern = r'(?:USD|US\$)[\s]*(\d+(?:[.,]\d+)?)\s*(?:million|m|bn|billion|k|thousand)?'
        for match in re.finditer(usd_pattern, text, re.IGNORECASE):
            amount = match.group(1)
            if amount:
                val = apply_scale(amount, match.group(0)) * 7.8
                if val > 0:
                    result["usd"].append(val)
        rmb_pattern = r'(?:RMB|CNY)[\s]*(\d+(?:[.,]\d+)?)\s*(?:million|m|bn|billion|k|thousand)?'
        for match in re.finditer(rmb_pattern, text, re.IGNORECASE):
            amount = match.group(1)
            if amount:
                val = apply_scale(amount, match.group(0)) * 1.1
                if val > 0:
                    result["rmb"].append(val)
        numbers = QueryParser.extract_numbers(text)
        if not result["hk_dollars"] and not result["usd"] and not result["rmb"] and numbers:
            result["raw_numbers"] = numbers
        return {k: v for k, v in result.items() if v}
    
    @staticmethod
    def extract_percentages(text: str) -> List[float]:
        if not text:
            return []
        percentages = []
        for match in re.findall(r'([0-9]*\.?[0-9]+)\s*%', text):
            try:
                percentages.append(float(match))
            except ValueError:
                continue
        for match in re.findall(r'([0-9]*\.?[0-9]+)\s*(?:percent|percentage)', text, re.IGNORECASE):
            try:
                val = float(match)
                if val not in percentages:
                    percentages.append(val)
            except ValueError:
                continue
        for match in re.findall(r'百分之(\d+)', text):
            try:
                val = float(match)
                if val not in percentages:
                    percentages.append(val)
            except ValueError:
                continue
        return sorted(list(set(percentages)))
    
    @staticmethod
    def extract_transaction_type(text: str):
        if not text:
            return None
        text_lower = text.lower()
        patterns_acq = [r'acquis(ition|e|ing)?', r'acquir(ing|e)', r'buy(ing)?', r'purchas(e|ing)', r'takeover', r'consolidat(e|ion)']
        for pattern in patterns_acq:
            if re.search(pattern, text_lower):
                return "acquisition"
        patterns_disp = [r'dispos(e|al)', r'sell(ing|s)?', r'sold', r'divest(ing)?']
        for pattern in patterns_disp:
            if re.search(pattern, text_lower):
                return "disposal"
        return None
    
    @staticmethod
    def extract_classification_tier(text: str):
        if not text:
            return None
        text_lower = text.lower()
        tiers = [(r'very\s+substantial', "very_substantial"), (r'major\s+transaction|is\s+major', "major_transaction"), (r'de\s+minimis', "de_minimis"), (r'discloseable\s+transaction', "discloseable_transaction"), (r'share\s+transaction', "share_transaction")]
        for pattern, tier_name in tiers:
            if re.search(pattern, text_lower):
                return tier_name
        return None
    
    @staticmethod
    def extract_rule_reference(text: str):
        if not text:
            return None
        match = re.search(r'(?:Rule|Section|规则)?\s*(\d+[A-Z]?\.\d+)(?!\w)', text, re.IGNORECASE)
        if match:
            rule_ref = match.group(1)
            if re.match(r'\d+[A-Z]?\.\d+$', rule_ref):
                return rule_ref
        return None
    
    @staticmethod
    def normalize_field_name(text: str) -> str:
        if not text:
            return ""
        normalized = text.lower().strip()
        valid_fields = {"issuer_market_cap", "issuer_total_assets", "issuer_net_assets", "issuer_annual_profit", "issuer_shares_outstanding", "transaction_consideration", "acquired_assets", "acquired_profit", "acquired_net_assets", "transaction_type"}
        if normalized in valid_fields:
            return normalized
        # More specific patterns first (acquired patterns before general profit pattern)
        mappings = [
            (r'acquired\s+assets', 'acquired_assets'),
            (r'acquired\s+profit', 'acquired_profit'),
            (r'acquired\s+net', 'acquired_net_assets'),
            (r'(issuer\s+)?market\s+cap', 'issuer_market_cap'),
            (r'total\s+assets', 'issuer_total_assets'),
            (r'net\s+assets', 'issuer_net_assets'),
            (r'(annual\s+)?profit', 'issuer_annual_profit'),
            (r'(shares|outstanding)', 'issuer_shares_outstanding'),
            (r'consideration', 'transaction_consideration'),
            (r'(transaction\s+)?type', 'transaction_type'),
        ]
        for pattern, field_name in mappings:
            if re.search(pattern, normalized):
                return field_name
        return normalized.replace(' ', '_')
