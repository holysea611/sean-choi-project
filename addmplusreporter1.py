import streamlit as st
import re
import json
import pandas as pd

# ==========================================
# 1. 수식 오타/문법 검수 클래스 (최우선 실행)
# ==========================================
class MathFormulaInspector:
    def __init__(self):
        self.log = []

    def get_context(self, text, start, end, window=15):
        s = max(0, start - window)
        e = min(len(text), end + window)
        context = text[s:e].replace('\n', ' ')
        return f"...{context}..."

    def check_parentheses(self, formula, offset, full_text):
        """괄호 짝 검사 (LaTeX의 \{, \}는 제외하고 구조적 괄호만 검사)"""
        # LaTeX의 \{, \}는 괄호 짝 검사에서 무시하기 위해 임시로 치환
        temp_formula = formula.replace(r'\{', '..').replace(r'\}', '..')
        
        stack = []
        mapping = {')': '(', '}': '{', ']': '['}
        
        for i, char in enumerate(temp_formula):
            if char in mapping.values(): # 여는 괄호
                stack.append((char, i))
            elif char in mapping.keys(): # 닫는 괄호
                if not stack or stack[-1][0] != mapping[char]:
                    context = self.get_context(full_text, offset+i, offset+i+1)
                    self.log.append({
                        "유형": "괄호 오류",
                        "문맥": context,
                        "대상": f"${formula}$",
                        "내용": f"닫는 괄호 '{char}'의 짝이 맞지 않음"
                    })
                    if stack: stack.pop()
                else:
                    stack.pop()
        
        if stack:
            for char, i in stack:
                context = self.get_context(full_text, offset+i, offset+i+1)
                self.log.append({
                    "유형": "괄호 오류",
                    "문맥": context,
                    "대상": f"${formula}$",
                    "내용": f"여는 괄호 '{char}'가 닫히지 않음"
                })

    def check_bad_patterns(self, formula, offset, full_text):
        """금지된 패턴 검사"""
        # 1. 곱하기 기호 * 사용
        if re.search(r'\d\s*\*\s*\d', formula):
            self.log.append({
                "유형": "표기 오류",
                "문맥": self.get_context(full_text, offset, offset+len(formula)),
                "대상": f"${formula}$",
                "내용": "곱하기 기호 '*' 사용됨 ($\\times$ 권장)"
            })
        
        # 2. 부등호 <=, >= 사용
        if '<=' in formula or '>=' in formula:
             self.log.append({
                "유형": "표기 오류",
                "문맥": self.get_context(full_text, offset, offset+len(formula)),
                "대상": f"${formula}$",
                "내용": "부등호 '<=', '>=' 사용됨 ($\\le, \\ge$ 권장)"
            })
             
        # 3. \frac 인자 누락 의심
        if '\\frac' in formula and not re.search(r'\\frac\s*\{', formula):
             self.log.append({
                "유형": "문법 오류",
                "문맥": self.get_context(full_text, offset, offset+len(formula)),
                "대상": f"${formula}$",
                "내용": "\\frac 명령어 인자 누락 의심"
            })

    def check_arithmetic(self, text):
        """단순 정수 사칙연산 검증 (전체 텍스트 대상)"""
        # 예: 12 + 3 = 15 (공백 허용, 정수만)
        # 보안을 위해 정규식으로 엄격하게 숫자와 연산자만 추출
        equation_pattern = re.compile(r'(?<![\.\d])(\d+[\s\+\-\*\/]+\d+\s*=\s*\d+)(?![\.\d])')
        matches = equation_pattern.finditer(text)
        
        for m in matches:
            eq_str = m.group(1)
            try:
                lhs, rhs = eq_str.split('=')
                # eval 사용 전 안전장치: 숫자, 공백, 연산자만 있는지 재확인
                if not re.match(r'^[\d\s\+\-\*\/]+$', lhs): continue
                
                calculated = eval(lhs)
                target = int(rhs)
                
                if calculated != target:
                    self.log.append({
                        "유형": "계산 오류",
                        "문맥": self.get_context(text, m.start(), m.end()),
                        "대상": eq_str,
                        "내용": f"계산 불일치 (좌변 결과: {calculated})"
                    })
            except:
                pass # 0으로 나누기 등 예외 무시

    def run(self, text):
        self.log = []
        
        # 1. LaTeX 수식 내부 검사 ($...$)
        latex_pattern = re.compile(r'\$([^\$]+)\$')
        for m in latex_pattern.finditer(text):
            formula = m.group(1)
            start_idx = m.start()
            
            self.check_parentheses(formula, start_idx, text)
            self.check_bad_patterns(formula, start_idx, text)
            
        # 2. 전체 텍스트 대상 산술 연산 검사
        self.check_arithmetic(text)
        
        return self.log

# ==========================================
# 2. 수식 조사 호응 교정 클래스
# ==========================================
class JosaCorrector:
    def __init__(self):
        self.log = []
        self.batchim_dict = self._init_batchim_dict()
        self.unit_batchim_dict = self._init_unit_batchim_dict()
        self.particle_pairs = self._init_particle_pairs()
        
        self.protected_words = [
            '이다', '입니다', '이므로', '이며', '이고', '이나', '이면서', '이지만', '이어서',
            '이때', '이어야', '가지',
            '이면', # [보호] 쉼표 뒤 '이면' 유지
            '이상', '이하', '이내', '이외', '미만', '초과',
            '이은', '이을', '이어', '이으므로', '이어진', '이루어진', '이루는', '이동', '이용',
            '없는', '있는', '없고', '있고', '없이', '있어', '없어'
        ]

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
            ('이때', '이때'), ('이어야 하므로', '이어야 하므로'),
            ('가지', '가지'),
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
        current = latex_str.replace(r'\left', '').replace(r'\right', '')
        prev_str = ""
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

        split_pattern = (r'=|\\approx|\\ne|>|<|\\ge|\\le|\\times|\\div|'
                         r'(?<!\^)\+|(?<!\^)-|\\cdot|'
                         r'\\cap|\\cup|\\setminus|\\subset|\\subseteq|\\in|\\ni')
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
        for word in self.protected_words:
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

    def clean_latex_for_human(self, latex):
        text = re.sub(r'\\(left|right|mathrm|text|bf|it)', '', latex)
        text = text.replace('{', '').replace('}', '').replace('\\', '')
        return text.strip()

    def get_context(self, text, start, end, window=10):
        s = max(0, start - window)
        e = min(len(text), end + window)
        context = text[s:e].replace('\n', ' ')
        return f"...{context}..."

    def run(self, raw_input):
        self.log = [] 
        try:
            if isinstance(raw_input, dict): input_data = raw_input
            else: input_data = json.loads(raw_input)
            target_text = input_data.get("result", raw_input) if isinstance(input_data, dict) else str(raw_input)
        except:
            target_text = str(raw_input)

        def replacer(match):
            pre, s1, formula, s2, particle = match.groups()
            p_match = re.search(r'[가-힣]+', particle)
            
            match_start = match.start()
            match_end = match.end()

            if not p_match:
                if '.' in particle:
                    new_particle = particle.replace('.', '')
                    human_readable = self.clean_latex_for_human(formula)
                    context = self.get_context(target_text, match_start, match_end)
                    self.log.append({
                        "문맥": context,
                        "대상": human_readable,
                        "원문": particle,
                        "수정": new_particle,
                        "사유": "불필요한 마침표 제거"
                    })
                    return f"{pre}{s1}${formula}${s2}{new_particle}"
                return match.group(0)

            p_start = p_match.start()
            original_p = p_match.group()
            remaining_particle = particle[p_start:]
            
            for word in self.protected_words:
                if remaining_particle.startswith(word): return match.group(0)
                
            target = self.find_target(formula)
            correct_p = self.get_correct_p(target, original_p)
            
            if original_p != correct_p:
                human_readable = self.clean_latex_for_human(formula)
                context = self.get_context(target_text, match_start, match_end)
                self.log.append({
                    "문맥": context,
                    "대상": human_readable,
                    "원문": original_p,
                    "수정": correct_p,
                    "사유": "받침 호응 오류"
                })

            return f"{pre}{s1}${formula}${s2}{particle[:p_start]}{correct_p}{particle[p_match.end():]}"

        pattern = r'([^$]*?)(\s*)\$([^\$]+)\$(\s*)([\s,]*[가-힣\s\.\?\!]+)'
        fixed_text = re.sub(pattern, replacer, target_text, flags=re.DOTALL)
        return fixed_text, self.log

# ==========================================
# 3. 한글 맞춤법/오타/조사 교정 클래스
# ==========================================
class SpellingCorrector:
    def __init__(self):
        self.log = []
        self.typo_dict = {
            "최대값": "최댓값", "최소값": "최솟값", "극대값": "극댓값", "극소값": "극솟값",
            "절대값": "절댓값", "근사값": "근삿값", "대표값": "대푯값", "함수값": "함숫값",
            "꼭지점": "꼭짓점", "촛점": "초점", "갯수": "개수", "나누기": "나눗셈",
            "않되": "안 되", "않돼": "안 돼", "않된다": "안 된다", "문안": "무난",
            "금새": "금세", "역활": "역할", "제작년": "재작년", "어떻해": "어떡해",
            "몇일": "며칠", "들어나다": "드러나다", "가르키다": "가리키다", "맞추다": "맞히다"
        }
        self.korean_particle_pairs = [
            ('은', '는'), ('이', '가'), ('을', '를'), ('과', '와'), ('으로', '로')
        ]
        
        self.exceptions = {
            '증가', '추가', '결과', '효과', '초과', '교과', '부과', '사과', '투과',
            '평가', '원가', '정가', '단가', '시가',
            '사이', '차이', '나이', '아이', '오이', '놀이',
            '경로', '진로', '선로', '항로',
            '없는', '있는', '갖는', '맞는', '맡는', '웃는', '씻는', '깎는', '볶는', '않는',
            '이은', '이을', '이어', '이어서', '깊은', '높은', '작은', '좁은',
            '인가', '는가', '은가', '던가', '나', '가' 
        }

    def has_batchim(self, char):
        if '가' <= char <= '힣':
            return (ord(char) - 0xAC00) % 28 > 0
        return False

    def is_rieul_batchim(self, char):
        if '가' <= char <= '힣':
            return (ord(char) - 0xAC00) % 28 == 8
        return False

    def get_context(self, text, start, end, window=10):
        s = max(0, start - window)
        e = min(len(text), end + window)
        context = text[s:e].replace('\n', ' ')
        return f"...{context}..."

    def run(self, text):
        self.log = []
        parts = re.split(r'(\$[^\$]+\$)', text)
        final_parts = []
        
        for i, part in enumerate(parts):
            if i % 2 == 1: 
                final_parts.append(part)
                continue
            
            current_text = part
            
            for wrong, correct in self.typo_dict.items():
                if wrong in current_text:
                    for m in re.finditer(re.escape(wrong), current_text):
                        context = self.get_context(current_text, m.start(), m.end())
                        self.log.append({
                            "문맥": context,
                            "대상": wrong,
                            "원문": wrong,
                            "수정": correct,
                            "사유": "맞춤법/표준어 오류"
                        })
                    current_text = current_text.replace(wrong, correct)
            
            pattern = r'([가-힣㉠-㉭])(은|는|이|가|을|를|과|와|으로|로)(?![가-힣])'
            
            def josa_replacer(match):
                full_word = match.group(0)
                if full_word in self.exceptions:
                    return full_word
                
                noun_char = match.group(1)
                josa = match.group(2)
                
                if '가' <= noun_char <= '힣':
                    has_bat = self.has_batchim(noun_char)
                    is_rieul = self.is_rieul_batchim(noun_char)
                else: 
                    has_bat = True
                    is_rieul = (noun_char == '㉣')

                correct_josa = josa
                for bat_o, bat_x in self.korean_particle_pairs:
                    if josa == bat_o or josa == bat_x:
                        if bat_o == '으로':
                            if not has_bat or is_rieul: correct_josa = '로'
                            else: correct_josa = '으로'
                        else:
                            correct_josa = bat_o if has_bat else bat_x
                        break
                
                if josa != correct_josa:
                    context = self.get_context(current_text, match.start(), match.end())
                    self.log.append({
                        "문맥": context,
                        "대상": full_word,
                        "원문": josa,
                        "수정": correct_josa,
                        "사유": "조사 호응 오류"
                    })
                    return f"{noun_char}{correct_josa}"
                return match.group(0)

            current_text = re.sub(pattern, josa_replacer, current_text)
            final_parts.append(current_text)
            
        return "".join(final_parts), self.log

# ==========================================
# 4. 메인 UI (Streamlit)
# ==========================================
st.set_page_config(page_title="수학 문제 통합 교정기", layout="wide")

st.title("✨ 수학 문제 통합 교정기")
st.markdown("""
**1단계: 수식 오류 검사** (괄호, 표기법, 계산 오류를 먼저 확인합니다)  
**2단계: 텍스트 교정** (수식 조사 호응, 한글 맞춤법을 교정합니다)
""")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("입력 (Input)")
    input_val = st.text_area("텍스트를 입력하세요:", height=600, 
                             placeholder="예: $A = \{ x | x > 0 $ (괄호 오류), 3 + 5 = 9 (계산 오류)")

with col2:
    st.subheader("검수 리포트 (Report)")
    
    if input_val:
        # [Step 1] 수식 오타 검수 (원본 텍스트 기준)
        math_inspector = MathFormulaInspector()
        math_logs = math_inspector.run(input_val)
        
        # 수식 오류가 있으면 최상단에 경고 표시
        if math_logs:
            st.error(f"🚨 수식/계산 오류가 {len(math_logs)}건 발견되었습니다! 먼저 수정해주세요.")
            df_math = pd.DataFrame(math_logs)
            st.dataframe(df_math[['유형', '문맥', '대상', '내용']], use_container_width=True, hide_index=True)
            st.markdown("---") # 구분선
        
        # [Step 2] 텍스트 교정 실행 (수식 오류와 무관하게 진행)
        # 1. 조사 교정
        josa_corrector = JosaCorrector()
        temp_text, josa_logs = josa_corrector.run(input_val)
        
        # 2. 맞춤법 교정
        spell_corrector = SpellingCorrector()
        final_text, spell_logs = spell_corrector.run(temp_text)
        
        # --- 탭으로 상세 리포트 출력 ---
        tab1, tab2 = st.tabs(["🔍 수식 조사 검수", "📝 한글/기호 검수"])
        
        with tab1:
            if josa_logs:
                st.warning(f"수식 조사 오류: {len(josa_logs)}건")
                df_josa = pd.DataFrame(josa_logs)
                st.dataframe(df_josa[['문맥', '대상', '원문', '수정', '사유']], use_container_width=True, hide_index=True)
            else:
                st.success("수식 조사가 완벽합니다.")
                
        with tab2:
            if spell_logs:
                st.warning(f"한글/기호 오류: {len(spell_logs)}건")
                df_spell = pd.DataFrame(spell_logs)
                st.dataframe(df_spell[['문맥', '대상', '원문', '수정', '사유']], use_container_width=True, hide_index=True)
            else:
                st.success("발견된 오타가 없습니다.")

        st.markdown("---")
        st.subheader("최종 결과물 (Result)")
        st.text_area("교정된 텍스트", value=final_text, height=300)
        
        st.download_button(
            label="💾 결과 파일 다운로드",
            data=final_text,
            file_name="corrected_result.txt",
            mime="text/plain"
        )
    else:
        st.info("왼쪽에 내용을 입력하면 자동으로 검사를 시작합니다.")