import re
from typing import List, Dict, Tuple, Optional
from pydantic import BaseModel, Field
from collections import defaultdict

from app.retrieval.hybrid_retriever import RetrievalResult
from app.core.logger import logger


class Contradiction(BaseModel):
    claim: str = Field(..., description="Contradictory claim text")
    chunk_a_id: str = Field(..., description="First chunk ID")
    chunk_b_id: str = Field(..., description="Second chunk ID")
    description: str = Field(default="", description="Description of contradiction")
    contradiction_type: str = Field(default="unknown", description="Type: numeric, conditional, scope")


class KeyClaim(BaseModel):
    """Extracted key claim from a chunk"""
    chunk_id: str
    claim_type: str  # "numeric", "conditional", "general"
    claim_text: str
    rule_number: Optional[str] = None
    subject: Optional[str] = None  # e.g., "disclosure", "threshold"
    value: Optional[str] = None  # e.g., "5%", "1000万"
    condition: Optional[str] = None  # For conditional claims


class VerificationResult(BaseModel):
    claim_support_map: Dict[str, List[str]] = Field(default_factory=dict)
    unsupported_claims: List[str] = Field(default_factory=list)
    contradictions: List[Contradiction] = Field(default_factory=list)
    confidence_level: str = Field(default="medium")
    revision_needed: bool = Field(default=False)


class AnswerVerifier:
    # Overlap thresholds for claim support detection
    SHORT_CLAIM_THRESHOLD = 0.6  # Claims ≤5 words
    MEDIUM_CLAIM_THRESHOLD = 0.5  # Claims 6-10 words
    LONG_CLAIM_THRESHOLD = 0.4   # Claims >10 words
    SHORT_CLAIM_MAX_WORDS = 5
    MEDIUM_CLAIM_MAX_WORDS = 10

    def __init__(self, min_support_threshold: float = 0.5):
        self.min_support_threshold = min_support_threshold

        # Legal term synonyms (refined to true legal equivalents)
        self.legal_synonyms = {
            "披露": ["公开", "公布"],
            "要求": ["规定", "需要", "应当", "必须"],
            "豁免": ["免除", "例外"],
            "上市": ["挂牌"],
            "股东": ["持股人"],
            "董事": ["理事"],
            "交易": ["买卖", "转让"],
            "关联": ["相关"],
            "公告": ["通知", "公示"],
            "报告": ["申报"],
        }

        # Build reverse lookup: word -> canonical for O(1) lookup
        self.word_to_canonical = {}
        for canonical, synonyms in self.legal_synonyms.items():
            self.word_to_canonical[canonical] = canonical
            for syn in synonyms:
                self.word_to_canonical[syn] = canonical
    
    def verify(self, answer: str, results: List[RetrievalResult]) -> VerificationResult:
        claims = self._extract_claims(answer)
        
        claim_support_map: Dict[str, List[str]] = {}
        unsupported_claims: List[str] = []
        
        for claim in claims:
            supporting_chunk_ids = self._find_supporting_chunks(claim, results)
            claim_support_map[claim] = supporting_chunk_ids
            
            if not supporting_chunk_ids:
                unsupported_claims.append(claim)
        
        contradictions = self._detect_contradictions(results)
        
        confidence_level = self._calculate_confidence(claims, unsupported_claims, results)
        
        revision_needed = len(unsupported_claims) > 0 or len(contradictions) > 0
        
        verification = VerificationResult(
            claim_support_map=claim_support_map,
            unsupported_claims=unsupported_claims,
            contradictions=contradictions,
            confidence_level=confidence_level,
            revision_needed=revision_needed
        )
        
        logger.info(f"Verification: {len(unsupported_claims)} unsupported claims, confidence={confidence_level}")
        return verification
    
    def _extract_claims(self, answer: str) -> List[str]:
        """Extract individual claims from an answer.

        Recognizes:
        - Conditional claims (if-then patterns)
        - Threshold claims (numeric thresholds)
        - Regular sentences (fallback)
        """
        claims = []

        # Pattern 1: Chinese conditional claims (如果...则...)
        cond_patterns = [
            (r'如果(.+?)，则(.+?)[。；]', 'if_then'),
            (r'若(.+?)，则(.+?)[。；]', 'if_then'),
        ]
        for pattern, _ in cond_patterns:
            for match in re.finditer(pattern, answer):
                claims.append(f"IF: {match.group(1).strip()} THEN: {match.group(2).strip()}")

        # Pattern 2: Threshold claims (超过X%需要Y)
        threshold_pattern = r'超过(\d+(?:\.\d+)?%?)[的]?(?:需要|应当|必须)?(.{5,30}?)[。；]'
        for match in re.finditer(threshold_pattern, answer):
            claims.append(f"THRESHOLD: {match.group(1)} -> {match.group(2).strip()}")

        # Pattern 3: Obligation claims (应当/必须/需要 + action)
        obligation_pattern = r'(?:上市发行人|上市公司|公司)?(?:应当|必须|需要|须)(.{5,50}?)[。；]'
        for match in re.finditer(obligation_pattern, answer):
            obligation = match.group(0).strip()
            if obligation not in claims:
                claims.append(obligation)

        # Pattern 4: Regular sentences (English and Chinese)
        for sentence in re.split(r'[.!?。！？]+', answer):
            sentence = sentence.strip()
            # Skip short sentences, and ones already captured
            if len(sentence) > 15 and sentence not in claims:
                # Skip if this is part of a conditional or threshold claim already captured
                is_sub_claim = any(sentence in c for c in claims)
                if not is_sub_claim:
                    claims.append(sentence)

        return [c for c in claims if c]  # Filter empty strings
    
    def _find_supporting_chunks(self, claim: str, results: List[RetrievalResult]) -> List[str]:
        supporting: List[str] = []

        # Dynamic threshold based on claim length
        claim_words: List[str] = claim.split()
        if len(claim_words) <= self.SHORT_CLAIM_MAX_WORDS:
            threshold: float = self.SHORT_CLAIM_THRESHOLD
        elif len(claim_words) <= self.MEDIUM_CLAIM_MAX_WORDS:
            threshold = self.MEDIUM_CLAIM_THRESHOLD
        else:
            threshold = self.LONG_CLAIM_THRESHOLD

        for result in results:
            # Signal 1: Exact rule number citation (strongest signal)
            if result.chunk.rule_number and self._has_rule_citation(claim, result.chunk.rule_number):
                supporting.append(result.chunk_id)
                continue

            # Signal 2: Semantic overlap with synonym normalization
            semantic_score: float = self._semantic_overlap(claim, result.chunk.text)
            if semantic_score >= threshold:
                supporting.append(result.chunk_id)

        return supporting

    def _has_rule_citation(self, claim: str, rule_number: str) -> bool:
        """Check if a claim explicitly cites a rule number."""
        # Validate rule_number format first to prevent regex injection
        if not re.match(r'^[\w\d]+\.[\w\d]+$', rule_number):
            logger.warning(f"Invalid rule_number format: {rule_number}")
            return False
        # Normalize rule number format and use word boundaries
        rule_pattern = r'\b' + re.escape(rule_number).replace(r'\.', r'\.?') + r'\b'
        return bool(re.search(rule_pattern, claim, re.IGNORECASE))

    def _normalize_to_canonical(self, words: set) -> set:
        """Normalize words to canonical forms using synonym dictionary."""
        normalized = set()
        for word in words:
            canonical = self.word_to_canonical.get(word)
            if canonical:
                normalized.add(canonical)
            else:
                normalized.add(word)
        return normalized

    def _semantic_overlap(self, claim: str, chunk_text: str) -> float:
        """Calculate semantic overlap score with legal synonym normalization."""
        claim_lower = claim.lower()
        text_lower = chunk_text.lower()

        # Extended Chinese stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'for', 'on', 'with', 'by',
            '的', '了', '是', '在', '和', '与', '这', '那', '有', '为', '等', '及', '或', '但', '而'
        }

        # Simple tokenization (space-based for mixed content)
        claim_words = set(w for w in claim_lower.split() if w not in stop_words and len(w) > 1)
        text_words = set(w for w in text_lower.split() if w not in stop_words and len(w) > 1)

        if not claim_words:
            return 0.0

        # Normalize both sides to canonical forms
        claim_canonical = self._normalize_to_canonical(claim_words)
        text_canonical = self._normalize_to_canonical(text_words)

        overlap = claim_canonical & text_canonical
        base_score = len(overlap) / len(claim_canonical) if claim_canonical else 0.0

        return base_score
    
    def _detect_contradictions(self, results: List[RetrievalResult]) -> List[Contradiction]:
        """Detect contradictions between chunks."""
        contradictions: List[Contradiction] = []

        # Extract key claims from all chunks
        all_claims = self._extract_all_claims(results)

        # Detect numeric contradictions (different thresholds for same subject)
        numeric_contradictions = self._detect_numeric_contradictions(all_claims)
        contradictions.extend(numeric_contradictions)

        # Detect conditional contradictions (conflicting if-then statements)
        conditional_contradictions = self._detect_conditional_contradictions(all_claims)
        contradictions.extend(conditional_contradictions)

        # Detect scope contradictions (applies to X vs only applies to Y)
        scope_contradictions = self._detect_scope_contradictions(all_claims)
        contradictions.extend(scope_contradictions)

        logger.info(f"Detected {len(contradictions)} contradictions")
        return contradictions

    def _extract_all_claims(self, results: List[RetrievalResult]) -> List[KeyClaim]:
        """Extract key claims from all chunks."""
        all_claims: List[KeyClaim] = []
        for result in results:
            claims = self._extract_key_claims(result)
            all_claims.extend(claims)
        return all_claims

    def _extract_key_claims(self, result: RetrievalResult) -> List[KeyClaim]:
        """Extract key claims from a single chunk."""
        claims: List[KeyClaim] = []
        chunk = result.chunk
        text = chunk.text
        chunk_id = chunk.chunk_id
        rule_number = chunk.rule_number

        # Extract numeric claims (thresholds, percentages)
        numeric_claims = self._extract_numeric_claims(text, chunk_id, rule_number)
        claims.extend(numeric_claims)

        # Extract conditional claims (if-then statements)
        conditional_claims = self._extract_conditional_claims(text, chunk_id, rule_number)
        claims.extend(conditional_claims)

        return claims

    def _extract_numeric_claims(self, text: str, chunk_id: str, rule_number: Optional[str]) -> List[KeyClaim]:
        """Extract numeric thresholds and percentages from text."""
        claims: List[KeyClaim] = []

        # Pattern for Chinese percentage thresholds: 超过X%、高于X%等
        pct_patterns = [
            r'超过(\d+(?:\.\d+)?%?)',
            r'高于(\d+(?:\.\d+)?%?)',
            r'达到(\d+(?:\.\d+)?%?)',
            r'低于(\d+(?:\.\d+)?%?)',
            r'不超过(\d+(?:\.\d+)?%?)',
            r'须低于(\d+(?:\.\d+)?%?)',
        ]

        for pattern in pct_patterns:
            for match in re.finditer(pattern, text):
                value = match.group(0)
                # Find the subject before the percentage
                start = max(0, match.start() - 20)
                context = text[start:match.start()].strip()
                subject = self._extract_subject_from_context(context)

                claims.append(KeyClaim(
                    chunk_id=chunk_id,
                    claim_type="numeric",
                    claim_text=f"{value} (subject: {subject})",
                    rule_number=rule_number,
                    subject=subject,
                    value=value
                ))

        # Pattern for absolute values: 超过X万元、达到X万元
        abs_patterns = [
            r'超过(\d+(?:\.\d+)?(?:万|亿|千)?元)',
            r'达到(\d+(?:\.\d+)?(?:万|亿|千)?元)',
            r'不超过(\d+(?:\.\d+)?(?:万|亿|千)?元)',
            r'高于(\d+(?:\.\d+)?(?:万|亿|千)?元)',
        ]

        for pattern in abs_patterns:
            for match in re.finditer(pattern, text):
                value = match.group(0)
                start = max(0, match.start() - 20)
                context = text[start:match.start()].strip()
                subject = self._extract_subject_from_context(context)

                claims.append(KeyClaim(
                    chunk_id=chunk_id,
                    claim_type="numeric",
                    claim_text=f"{value} (subject: {subject})",
                    rule_number=rule_number,
                    subject=subject,
                    value=value
                ))

        return claims

    def _extract_subject_from_context(self, context: str) -> str:
        """Extract the subject from context before a threshold."""
        # Remove common prefixes
        context = re.sub(r'^(其中|且|并且|以及|以及|适用于|适用于|须|需要|应当|必须)+', '', context)
        context = context.strip()
        # Take last meaningful phrase
        words = context.split()
        if len(words) > 3:
            context = ' '.join(words[-3:])
        return context if context else "unknown"

    def _extract_conditional_claims(self, text: str, chunk_id: str, rule_number: Optional[str]) -> List[KeyClaim]:
        """Extract conditional if-then statements from text."""
        claims: List[KeyClaim] = []

        # Chinese conditional patterns
        conditional_patterns = [
            (r'如果(.+?)，则(.+?)[。；]', 'if_then'),
            (r'若(.+?)，则(.+?)[。；]', 'if_then'),
            (r'符合以下条件(.+?)：', 'condition_list'),
            (r'(.+?)的.+?条件[是为：](.+?)[。；]', 'condition_definition'),
        ]

        for pattern, cond_type in conditional_patterns:
            for match in re.finditer(pattern, text):
                if cond_type == 'if_then':
                    condition = match.group(1).strip()
                    consequence = match.group(2).strip()
                    claims.append(KeyClaim(
                        chunk_id=chunk_id,
                        claim_type="conditional",
                        claim_text=f"IF: {condition} THEN: {consequence}",
                        rule_number=rule_number,
                        condition=condition,
                        subject=consequence[:20] if consequence else "unknown"
                    ))

        return claims

    def _detect_numeric_contradictions(self, claims: List[KeyClaim]) -> List[Contradiction]:
        """Detect contradictions between numeric thresholds."""
        contradictions: List[Contradiction] = []

        # Group claims by (rule_number, subject)
        claim_groups: Dict[Tuple[str, str], List[KeyClaim]] = defaultdict(list)
        for claim in claims:
            if claim.claim_type == "numeric" and claim.rule_number and claim.subject:
                key = (claim.rule_number, claim.subject)
                claim_groups[key].append(claim)

        # Check for conflicting numeric values
        for (rule_number, subject), group_claims in claim_groups.items():
            if len(group_claims) < 2:
                continue

            # Extract numeric values for comparison
            values = []
            for claim in group_claims:
                numeric_value = self._extract_numeric_value(claim.value)
                if numeric_value is not None:
                    values.append((claim, numeric_value))

            # Check for conflicting directions (e.g., "超过5%" vs "不超过3%")
            if len(values) >= 2:
                for i, (claim_a, val_a) in enumerate(values):
                    for claim_b, val_b in values[i+1:]:
                        if self._is_conflicting_numeric(claim_a, val_a, claim_b, val_b):
                            contradictions.append(Contradiction(
                                claim=f"{subject}: {claim_a.value} vs {claim_b.value}",
                                chunk_a_id=claim_a.chunk_id,
                                chunk_b_id=claim_b.chunk_id,
                                description=f"Conflicting numeric thresholds for {subject} under {rule_number}",
                                contradiction_type="numeric"
                            ))

        return contradictions

    def _extract_numeric_value(self, value_str: Optional[str]) -> Optional[Tuple[float, str]]:
        """Extract numeric value and unit from string like '5%' or '1000万'."""
        if not value_str:
            return None

        # Handle percentage
        pct_match = re.match(r'(\d+(?:\.\d+)?)%?', value_str)
        if pct_match:
            return (float(pct_match.group(1)), '%')

        # Handle absolute values with Chinese units
        unit_match = re.match(r'(\d+(?:\.\d+)?)(万|亿|千)?元?', value_str)
        if unit_match:
            value = float(unit_match.group(1))
            unit = unit_match.group(2) or ''
            multiplier = {'万': 10000, '亿': 100000000, '千': 1000}.get(unit, 1)
            return (value * multiplier, unit)

        return None

    def _is_conflicting_numeric(self, claim_a: KeyClaim, val_a: Tuple[float, str], claim_b: KeyClaim, val_b: Tuple[float, str]) -> bool:
        """Check if two numeric claims conflict."""
        # Different units don't conflict
        if val_a[1] != val_b[1]:
            return False

        # Extract direction from original value strings
        val_a_str = claim_a.value or ''
        val_b_str = claim_b.value or ''

        # Get directions (超过=exceed, 不超过=not exceed, 低于=below)
        dir_a = 'increase' if '超' in val_a_str or '高' in val_a_str else ('decrease' if '低' in val_a_str or '不超' in val_a_str else 'neutral')
        dir_b = 'increase' if '超' in val_b_str or '高' in val_b_str else ('decrease' if '低' in val_b_str or '不超' in val_b_str else 'neutral')

        # If both say "exceed" but values differ significantly, no conflict
        if dir_a == dir_b and dir_a != 'neutral':
            return False

        # Check for actual conflicts
        # Example: "超过5%" (exceed 5%) vs "不超过3%" (not exceed 3%) - these conflict
        if ('超' in val_a_str or '高' in val_a_str) and ('不超' in val_b_str or '低' in val_b_str):
            if val_a[0] > val_b[0]:
                return True

        if ('超' in val_b_str or '高' in val_b_str) and ('不超' in val_a_str or '低' in val_a_str):
            if val_b[0] > val_a[0]:
                return True

        return False

    def _detect_conditional_contradictions(self, claims: List[KeyClaim]) -> List[Contradiction]:
        """Detect contradictions in conditional statements."""
        contradictions: List[Contradiction] = []

        # Group conditional claims by rule number
        cond_groups: Dict[str, List[KeyClaim]] = defaultdict(list)
        for claim in claims:
            if claim.claim_type == "conditional" and claim.rule_number:
                cond_groups[claim.rule_number].append(claim)

        for rule_number, group_claims in cond_groups.items():
            if len(group_claims) < 2:
                continue

            # Look for same condition but different consequences
            for i, claim_a in enumerate(group_claims):
                for claim_b in group_claims[i+1:]:
                    if self._is_contradicting_conditional(claim_a, claim_b):
                        contradictions.append(Contradiction(
                            claim=f"{claim_a.condition} -> {claim_a.subject} vs {claim_b.condition} -> {claim_b.subject}",
                            chunk_a_id=claim_a.chunk_id,
                            chunk_b_id=claim_b.chunk_id,
                            description=f"Conflicting conditions under {rule_number}",
                            contradiction_type="conditional"
                        ))

        return contradictions

    def _is_contradicting_conditional(self, claim_a: KeyClaim, claim_b: KeyClaim) -> bool:
        """Check if two conditional claims contradict each other."""
        # Same condition with opposite consequences
        cond_a = claim_a.condition or ""
        cond_b = claim_b.condition or ""

        # Check if conditions are the same/similar
        if not self._conditions_are_similar(cond_a, cond_b):
            return False

        # Check if consequences are contradictory
        cons_a = claim_a.subject or ""
        cons_b = claim_b.subject or ""

        # One says required, another says exempt/not required
        contradictory_pairs = [
            ('需要', '豁免'), ('需要', '无需'), ('应当', '无需'),
            ('必须', '可以不'), ('需要', '可以不'), ('适用', '不适用')
        ]

        for req, neg in contradictory_pairs:
            if (req in cons_a and neg in cons_b) or (req in cons_b and neg in cons_a):
                return True

        return False

    def _conditions_are_similar(self, cond_a: str, cond_b: str) -> bool:
        """Check if two conditions are similar enough to potentially conflict."""
        # Simple word overlap check
        words_a = set(cond_a.split())
        words_b = set(cond_b.split())
        overlap = words_a & words_b

        # If they share significant words, conditions are similar
        if len(overlap) >= 2:
            return True

        # Check for same rule number reference
        rule_ref_pattern = r'\d+[A-Z]?\.\d+'
        refs_a = set(re.findall(rule_ref_pattern, cond_a))
        refs_b = set(re.findall(rule_ref_pattern, cond_b))
        if refs_a and refs_a == refs_b:
            return True

        return False

    def _detect_scope_contradictions(self, claims: List[KeyClaim]) -> List[Contradiction]:
        """Detect contradictions about who/what a rule applies to."""
        contradictions: List[Contradiction] = []

        # Look for scope-related claims
        scope_claims: List[KeyClaim] = []
        for claim in claims:
            text = claim.claim_text.lower()
            if any(word in text for word in ['适用于', '适用于', '仅适用', '不适用', '例外', '豁免']):
                scope_claims.append(claim)

        # Group by rule number
        scope_groups: Dict[str, List[KeyClaim]] = defaultdict(list)
        for claim in scope_claims:
            if claim.rule_number:
                scope_groups[claim.rule_number].append(claim)

        for rule_number, group_claims in scope_groups.items():
            if len(group_claims) < 2:
                continue

            for i, claim_a in enumerate(group_claims):
                for claim_b in group_claims[i+1:]:
                    if self._is_scope_conflict(claim_a, claim_b):
                        contradictions.append(Contradiction(
                            claim=f"{claim_a.claim_text} vs {claim_b.claim_text}",
                            chunk_a_id=claim_a.chunk_id,
                            chunk_b_id=claim_b.chunk_id,
                            description=f"Conflicting scope for {rule_number}",
                            contradiction_type="scope"
                        ))

        return contradictions

    def _is_scope_conflict(self, claim_a: KeyClaim, claim_b: KeyClaim) -> bool:
        """Check if two claims have conflicting scope."""
        text_a = claim_a.claim_text
        text_b = claim_b.claim_text

        # One says applies, another says doesn't apply
        applies_patterns = ['适用于', '适用']
        exempt_patterns = ['不适用', '豁免', '例外', '仅适用']

        has_applies_a = any(p in text_a for p in applies_patterns)
        has_exempt_a = any(p in text_a for p in exempt_patterns)
        has_applies_b = any(p in text_b for p in applies_patterns)
        has_exempt_b = any(p in text_b for p in exempt_patterns)

        # Conflict: one says applies, another says exempt
        if (has_applies_a and has_exempt_b) or (has_applies_b and has_exempt_a):
            return True

        return False
    
    def _calculate_confidence(self, claims: List[str], unsupported: List[str], results: List[RetrievalResult]) -> str:
        if not claims:
            return "low"
        
        support_ratio = 1 - (len(unsupported) / len(claims))
        
        if support_ratio >= 0.8 and len(results) >= 3:
            return "high"
        elif support_ratio >= 0.5:
            return "medium"
        else:
            return "low"
