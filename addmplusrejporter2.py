import streamlit as st
import re
import json
import pandas as pd

# ==========================================
# 1. 수식 오타/문법 검수 클래스
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
        temp_formula = formula.replace(r'\{', '..').replace(r'\}', '..')
        stack = []
        mapping = {')': '(', '}': '{', ']': '['}
        
        for i, char in enumerate(temp_formula):
            if char in mapping.values():
                stack.append((char, i))
            elif char in mapping.keys():
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
        if re.search(r'\d\s*\*\s*\d', formula):
            self.log.append({"유형": "표기 오류", "문맥": self.get_context(full_text, offset, offset+len(formula)), "대상": f"${formula}$", "내용": "곱하기 기호 '*' 사용됨 ($\\times$ 권장)"})
        if '<=' in formula or '>=' in formula:
             self.log.append({"유형": "표기 오류", "문맥": self.get_context(full_text, offset, offset+len(formula)), "대상": f"${formula}$", "내용": "부등호 '<=', '>=' 사용됨 ($\\le, \\ge$ 권장)"})
        if '\\frac' in formula and not re.search(r'\\frac\s*\{', formula):
             self.log.append({"유형": "문법 오류", "문맥": self.get_context(full_text, offset, offset+len(formula)), "대상": f"${formula}$", "내용": "\\frac 명령어 인자 누락 의심"})

    def check_arithmetic(self, text):
        equation_pattern = re.compile(r'(?<![\.\d])(\d+[\s\+\-\*\/]+\d+\s*=\s*\d+)(?![\.\d])')
        matches = equation_pattern.finditer(text)
        for m in matches:
            eq_str = m.group(1)
            try:
                lhs, rhs = eq_str.split('=')
                if not re.match(r'^[\d\s\+\-\*\/]+$', lhs): continue
                calculated = eval(lhs)
                target = int(rhs)
                if calculated != target:
                    self.log.append({"유형": "계산 오류", "문맥": self.get_context(text, m.start(), m.end()), "대상": eq_str, "내용": f"계산 불일치 (좌변 결과: {calculated})"})
            except: pass

    def run(self, text):
        self.log = []
        latex_pattern = re.compile(r'\$([^\$]+)\$')
        for m in latex_pattern.finditer(text):
            formula = m.group(1)
            self.check_parentheses(formula, m.start(), text)
            self.check_bad_patterns(formula, m.start(), text)
        self.check_arithmetic(text)
        return self.log

# ==========================================
# 2. 수식 조사 호응 교정 클래스 (개선됨)
# ==========================================
class JosaCorrector:
    def __init__(self):
        self.log = []
        self.batchim_dict = self._init_batchim_dict()
        self.unit_batchim_dict = self._init_unit_batchim_dict()
        self.particle_pairs = [
            ('이므로', '므로'), ('이라서', '라서'), ('이라고', '라고'), 
            ('이라', '라'), ('이면', '면'), ('은', '는'), ('이', '가'), 
            ('을', '를'), ('과', '와'), ('으로', '로')
        ]
        # '이므로'는 받침 유무와 상관없이 체언 뒤에 붙을 수 있으므로 보호막 처리
        self.protected_words = [
            '이므로', '이다', '입니다', '이며', '이고', '이나', '이면서', '이지만', 
            '이어서', '이때', '이어야', '가지', '이상', '이하', '이내', '이외', 
            '미만', '초과', '이은', '이을', '이어', '이동', '이용'
        ]

    def _init_batchim_dict(self):
        # n, m, l, r 등 받침 소리가 나는 알파벳 정의
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
        return {'g': True, 'kg': True, 'mg': True, 'm': False, 'cm': False, 'km': False, 'l': False}

    def simplify_formula(self, latex_str):
        # 간단하게 마지막 글자만 추출하기 위해 LaTeX 태그 제거
        clean = re.sub(r'\\[a-zA-Z]+', '', latex_str)
        clean = re.sub(r'[\{\}\(\)\s\^]', '', clean)
        return clean

    def find_target(self, formula_str):
        # 수식의 마지막 의미 요소 파악
        if r'\degree' in formula_str or r'^\circ' in formula_str: return "도"
        if "C" in formula_str and "^" in formula_str: return "여집합"
        if "^" in formula_str and not formula_str.endswith("}"): return "제곱"
        
        simplified = self.simplify_formula(formula_str)
        if not simplified: return ""
        return simplified[-1]

    def get_correct_p(self, target, original_p):
        # 1. 보호 단어 확인 (예: '이므로'는 받침 없어도 'a이므로' 가능하므로 통과)
        for word in self.protected_words:
            if original_p.startswith(word): return original_p

        # 2. 받침 판정
        has_batchim = False
        if target in self.batchim_dict:
            has_batchim = self.batchim_dict[target]
        elif '가' <= target <= '힣':
            has_batchim = (ord(target) - 0xAC00) % 28 > 0
        
        is_rieul = target in ['1', '7', '8', 'L', 'R', 'l', 'r', 'ㄹ']

        # 3. 조사 쌍 검사
        for has_b, no_b in self.particle_pairs:
            if original_p.startswith(has_b) or original_p.startswith(no_b):
                if has_b == '으로':
                    stem = '으로' if (has_batchim and not is_rieul) else '로'
                else:
                    # 핵심: 받침이 있으면 무조건 '이므로', 없으면 '므로' (단, '이므로'는 위에서 보호됨)
                    stem = has_b if has_batchim else no_b
                return stem + original_p[len(has_b if original_p.startswith(has_b) else no_b):]
        
        return original_p

    def run(self, text):
        self.log = []
        # 정규표현식 개선: 수식($...$) 바로 뒤에 붙은 한글 조사 포착
        # 그룹1: 수식 내용, 그룹2: 수식 뒤 공백, 그룹3: 이어지는 한글
        pattern = r'\$([^\$]+)\$(\s*)([가-힣]+)'
        
        def replacer(match):
            formula = match.group(1)
            space = match.group(2)
            particle_full = match.group(3)
            
            target = self.find_target(formula)
            if not target: return match.group(0)
            
            correct_p = self.get_correct_p(target, particle_full)
            
            if particle_full != correct_p:
                context = f"...${formula}${space}{particle_full}..."
                self.log.append({
                    "문맥": context,
                    "대상": f"${formula}$",
                    "원문": particle_full,
                    "수정": correct_p,
                    "사유": "수식 조사 호응 오류"
                })
                return f"${formula}${space}{correct_p}"
            return match.group(0)

        fixed_text = re.sub(pattern, replacer, text)
        return fixed_text, self.log

# ==========================================
# 3. 한글 맞춤법 클래스
# ==========================================
class SpellingCorrector:
    def __init__(self):
        self.log = []
        self.typo_dict = {
            "자리수": "자릿수", "최대값": "최댓값", "최소값": "최솟값",
            "갯수": "개수", "나누기": "나눗셈", "꼭지점": "꼭짓점"
        }

    def run(self, text):
        self.log = []
        new_text = text
        for wrong, correct in self.typo_dict.items():
            if wrong in new_text:
                matches = re.finditer(wrong, new_text)
                for m in matches:
                    self.log.append({"문맥": f"...{new_text[max(0, m.start()-5):min(len(new_text), m.end()+5)]}...", "대상": wrong, "원문": wrong, "수정": correct, "사유": "맞춤법 오류"})
                new_text = new_text.replace(wrong, correct)
        return new_text, self.log

# ==========================================
# 4. 메인 UI
# ==========================================
st.set_page_config(page_title="수학 문제 통합 교정기", layout="wide")
st.title("✨ 수학 문제 통합 교정기 (v1.1)")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("입력 (Input)")
    input_val = st.text_area("텍스트를 입력하세요:", height=400, 
                             placeholder="예: $n$므로 (오류), $a$므로 (정상), $a$이므로 (정상), 자리수 (오류)")

if input_val:
    # 검수 프로세스
    math_inspector = MathFormulaInspector()
    m_logs = math_inspector.run(input_val)
    
    josa_corrector = JosaCorrector()
    text_after_josa, j_logs = josa_corrector.run(input_val)
    
    spell_corrector = SpellingCorrector()
    final_text, s_logs = spell_corrector.run(text_after_josa)
    
    with col2:
        st.subheader("검수 결과")
        tab1, tab2, tab3 = st.tabs(["🧮 수식/계산", "🔍 수식 조사", "📝 맞춤법"])
        
        with tab1:
            if m_logs: st.table(pd.DataFrame(m_logs))
            else: st.success("수식 오류 없음")
            
        with tab2:
            if j_logs: st.table(pd.DataFrame(j_logs))
            else: st.success("조사 오류 없음")
            
        with tab3:
            if s_logs: st.table(pd.DataFrame(s_logs))
            else: st.success("맞춤법 오류 없음")

    st.markdown("---")
    st.subheader("최종 결과물")
    st.text_area("교정된 텍스트", value=final_text, height=200)