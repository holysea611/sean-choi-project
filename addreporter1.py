import streamlit as st
import re
import json
import pandas as pd

class JosaChecker:
    def __init__(self):
        self.log = [] # 변경 내역 저장소
        self.batchim_dict = self._init_batchim_dict()
        self.unit_batchim_dict = self._init_unit_batchim_dict()
        self.particle_pairs = self._init_particle_pairs()

    def _init_batchim_dict(self):
        d = {
            '0': True, '1': True, '3': True, '6': True, '7': True, '8': True, '10': True,
            'l': True, 'm': True, 'n': True, 'r': True, 
            'L': True, 'M': True, 'N': True, 'R': True,
            '제곱': True, '여집합': True, '바': False
        }
        for c in "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ": d[c] = True
        for ch in '2459AaBbCcDdEeFfGgHhIiJjKkOoPpQqSsTtUuVvWwXxeYyZz':
            if ch not in d: d[ch] = False
        return d

    def _init_unit_batchim_dict(self):
        return {
            'm': False, 'cm': False, 'mm': False, 'km': False,
            'g': True, 'kg': True, 'mg': True,
            'l': False, 'L': False, 'mL': False,
            'A': False, 'V': False, 'W': False, 'Hz': False,
            'deg': False, 'degree': False
        }

    def _init_particle_pairs(self):
        return [
            ('이다', '이다'), ('입니다', '입니다'),
            ('이므로', '이므로'), ('이며', '이며'), ('이고', '이고'), ('이나', '이나'),
            ('이면서', '이면서'), ('이지만', '이지만'), ('이어서', '이어서'),
            ('이때', '이때'), ('이어야 하므로', '이어야 하므로'), ('가지', '가지'),
            ('이라서', '라서'), ('이라고', '라고'), ('이라', '라'), ('이면', '면'), 
            ('은', '는'), ('이', '가'), ('을', '를'), ('과', '와'), ('으로', '로'), ('을', '울')
        ]

    def get_balanced(self, text, start_idx):
        if start_idx == -1 or start_idx >= len(text): return None, start_idx
        count = 0
        for i in range(start_idx, len(text)):
            if text[i] == '{': count += 1
            elif text[i] == '}': count -= 1
            if count == 0: return text[start_idx+1:i], i + 1
        return None, start_idx

    def simplify_formula(self, latex_str):
        prev_str = ""
        current = latex_str
        while prev_str != current:
            prev_str = current
            if '\\frac' in current:
                idx = current.find('\\frac')
                num, end_num = self.get_balanced(current, current.find('{', idx))
                _, end_den = self.get_balanced(current, current.find('{', end_num))
                if num is not None:
                    current = current[:idx] + num + current[end_den:]
                    continue
            if '\\sqrt' in current:
                idx = current.find('\\sqrt')
                if idx + 5 < len(current) and current[idx+5] == '[':
                    close_bracket = current.find(']', idx)
                    if close_bracket != -1:
                        current = current[:idx+5] + current[close_bracket+1:]
                        continue
            current = re.sub(r'\\left\s*\(|\\right\s*\)|\\left\s*\{|\\right\s*\}|\\left\s*\[|\\right\s*\]', '', current)
            stripped = current.strip()
            if stripped.startswith('{') and stripped.endswith('}'):
                content, end = self.get_balanced(stripped, 0)
                if end == len(stripped):
                    current = content
                    continue
        return current

    def find_target(self, formula_str):
        simplified = self.simplify_formula(formula_str)
        clean = re.sub(r'\s+', '', simplified)
        
        masked_text = clean
        braces_content = []
        while True:
            start = masked_text.find('{')
            if start == -1: break
            content, end_idx = self.get_balanced(masked_text, start)
            if content is None: break
            placeholder = f"@BRACE{len(braces_content)}@"
            braces_content.append(content)
            masked_text = masked_text[:start] + placeholder + masked_text[end_idx:]

        split_pattern = (
            r'=|\\approx|\\ne|>|<|\\ge|\\le|\\times|\\div|'
            r'(?<!\^)\+|(?<!\^)-|\\cdot|'
            r'\\cap|\\cup|\\setminus|\\subset|\\subseteq|\\in|\\ni'
        )
        parts = re.split(split_pattern, masked_text)
        final_term = parts[-1] if parts else masked_text

        while "@BRACE" in final_term:
            for i, content in enumerate(braces_content):
                placeholder = f"@BRACE{i}@"
                if placeholder in final_term:
                    final_term = final_term.replace(placeholder, "{" + content + "}")

        if r'\degree' in final_term or r'^\circ' in final_term: return "도"
        if "^" in final_term:
            if "C" in final_term: return "여집합"
            base_part = final_term.split('^')[0]
            mathrm_match = re.search(r'\\mathrm\{([a-zA-Z]+)\}', base_part)
            if mathrm_match:
                unit_content = mathrm_match.group(1)
                if unit_content in ['m', 'cm', 'mm', 'km']: return "미터"
            return "제곱"

        mathrm_match = re.search(r'\\mathrm\{([a-zA-Z]+)\}', final_term)
        if mathrm_match: return f"UNIT:{mathrm_match.group(1)}"

        if final_term.endswith(')'):
             m = re.search(r'([가-힣a-zA-Z0-9])\)+$', final_term)
             if m: return m.group(1)

        text_only = re.sub(r'\\[a-zA-Z]+|[{}]|[()\[\]]|[\.,]', '', final_term)
        text_only = text_only.replace('\\', '').strip() 
        return text_only[-1] if text_only else ""

    def get_correct_p(self, target, original_p):
        protected_words = ['이다', '이므로', '이며', '이나', '이고', '입니다', '이면서', '이지만', '이어서', '이때', '이어야 하므로', '가지']
        for word in protected_words:
            if original_p.startswith(word): return original_p

        if not target.startswith("UNIT:") and len(target) == 1 and re.match(r'[a-zA-Z0-9]', target):
            is_noun_mask = False
            if original_p.startswith('가면'):
                after_mask = original_p[2:]
                if after_mask and after_mask[0] in ['을', '이', '은', '과', '의', '로']: is_noun_mask = True
                if not is_noun_mask and original_p.startswith(('이면', '면', '가면')):
                    suffix = original_p[2:] if original_p.startswith('가면') else original_p[len('이면' if original_p.startswith('이면') else '면'):]
                    return '이면' + suffix

        has_batchim = False
        if target.startswith("UNIT:"):
            real_unit = target.split(":")[1]
            has_batchim = self.unit_batchim_dict.get(real_unit, False)
        elif target == "미터": has_batchim = False
        else:
            if target in self.batchim_dict: has_batchim = self.batchim_dict[target]
            elif len(target) == 1 and '가' <= target <= '힣': has_batchim = (ord(target) - 0xAC00) % 28 > 0
            elif len(target) > 1:
                last = target[-1]
                has_batchim = (ord(last) - 0xAC00) % 28 > 0 if '가' <= last <= '힣' else self.batchim_dict.get(last, False)
            else: has_batchim = self.batchim_dict.get(target, False)

        is_rieul = target in ['1', '7', '8', 'L', 'R', 'l', 'r', 'ㄹ']
        
        for has_b, no_b in self.particle_pairs:
            if original_p.startswith(has_b) or original_p.startswith(no_b):
                if has_b == '으로':
                    stem = '으로' if (has_batchim and not is_rieul) else '로'
                else:
                    stem = has_b if has_batchim else no_b
                return stem + original_p[len(has_b if original_p.startswith(has_b) else no_b):]
        return original_p

    def process_text(self, text):
        self.log = [] # 초기화

        def replacer(match):
            pre, s1, formula, s2, particle = match.groups()
            p_match = re.search(r'[가-힣]+', particle)
            
            if not p_match:
                if '.' in particle:
                    new_particle = particle.replace('.', '')
                    # 로그 기록: 마침표 제거
                    self.log.append({
                        "type": "format",
                        "formula": f"${formula}$",
                        "original": particle,
                        "corrected": new_particle,
                        "reason": "수식 뒤 불필요한 마침표 제거"
                    })
                    return f"{pre}{s1}${formula}${s2}{new_particle}"
                return match.group(0)

            p_start = p_match.start()
            original_p_text = p_match.group()
            remaining_particle = particle[p_start:]
            
            absolute_protected = ['이때', '이어야 하므로']
            for word in absolute_protected:
                if remaining_particle.startswith(word): return match.group(0)
                
            target = self.find_target(formula)
            correct_p_text = self.get_correct_p(target, original_p_text)
            
            # 변경사항이 있으면 로그에 기록
            if original_p_text != correct_p_text:
                self.log.append({
                    "type": "josa",
                    "formula": f"${formula}$",
                    "original": original_p_text,
                    "corrected": correct_p_text,
                    "reason": "받침 호응 오류"
                })

            return f"{pre}{s1}${formula}${s2}{particle[:p_start]}{correct_p_text}{particle[p_match.end():]}"

        pattern = r'([^$]*?)(\s*)\$([^\$]+)\$(\s*)([\s,]*[가-힣\s\.\?\!]+)'
        fixed_text = re.sub(pattern, replacer, text, flags=re.DOTALL)
        return fixed_text, self.log

# --- UI 구성 ---
st.set_page_config(page_title="수식 조사 호응 검수기", layout="wide")

st.title("🧐 수식 조사 호응 검수기")
st.markdown("텍스트를 입력하면 **조사 호응 오류를 검출**하고, **수정 요약 리포트**를 제공합니다.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. 입력 (Input)")
    input_raw = st.text_area("검수할 텍스트를 입력하세요:", height=500)

with col2:
    st.subheader("2. 검수 리포트 (Report)")
    
    if input_raw:
        checker = JosaChecker()
        
        # JSON 처리 시도
        try:
            data = json.loads(input_raw)
            target_text = data.get("result", input_raw) if isinstance(data, dict) else str(input_raw)
        except:
            target_text = input_raw
            
        # 검수 실행
        corrected_text, logs = checker.process_text(target_text)
        
        if logs:
            st.error(f"총 {len(logs)}건의 수정 사항이 발견되었습니다.")
            
            # 리포트 데이터프레임 생성
            df_log = pd.DataFrame(logs)
            
            # 보기 좋게 컬럼 이름 변경
            df_display = df_log[['formula', 'original', 'corrected', 'reason']].rename(columns={
                'formula': '대상 수식',
                'original': '원문 조사',
                'corrected': '추천 수정',
                'reason': '사유'
            })
            
            st.dataframe(df_display, use_container_width=True)
            
            st.markdown("---")
            st.markdown("### 📝 수정된 전체 텍스트")
            st.text_area("결과물", value=corrected_text, height=300)
            
        else:
            st.success("✅ 완벽합니다! 수정할 사항이 발견되지 않았습니다.")
            st.text_area("결과물", value=corrected_text, height=300)

    else:
        st.info("왼쪽에 텍스트를 입력하면 검수 결과가 표시됩니다.")