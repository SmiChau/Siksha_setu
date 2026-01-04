const sign_in_btn = document.querySelector("#sign-in-btn");
const sign_up_btn = document.querySelector("#sign-up-btn");
const container = document.querySelector(".container");

// Mobile toggles
const sign_in_btn_mobile = document.querySelector("#sign-in-btn-mobile");
const sign_up_btn_mobile = document.querySelector("#sign-up-btn-mobile");

// Mode Switching
function switchToSignUp() {
    container.classList.add("sign-up-mode");
}

function switchToSignIn() {
    container.classList.remove("sign-up-mode");
}

if (sign_up_btn) sign_up_btn.addEventListener("click", switchToSignUp);
if (sign_in_btn) sign_in_btn.addEventListener("click", switchToSignIn);

// Mobile listeners
if (sign_up_btn_mobile) {
    sign_up_btn_mobile.addEventListener("click", (e) => {
        e.preventDefault();
        switchToSignUp();
    });
}

if (sign_in_btn_mobile) {
    sign_in_btn_mobile.addEventListener("click", (e) => {
        e.preventDefault();
        switchToSignIn();
    });
}

// Password Validation (Simpler Version)
const passwordInput = document.querySelector('.password-input');
const rulesElements = document.querySelectorAll('.rule');

if (passwordInput) {
    passwordInput.addEventListener('input', function (e) {
        const value = e.target.value;

        const rules = {
            length: value.length >= 8,
            uppercase: /[A-Z]/.test(value),
            lowercase: /[a-z]/.test(value),
            number: /[0-9]/.test(value),
            special: /[!@#$%^&*(),.?":{}|<>]/.test(value)
        };

        // Update Rules UI
        rulesElements.forEach(item => {
            const ruleName = item.getAttribute('data-rule');
            if (rules[ruleName]) {
                item.classList.add('valid');
                item.querySelector('i').className = 'bx bxs-check-circle';
            } else {
                item.classList.remove('valid');
                item.querySelector('i').className = 'bx bx-circle';
            }
        });
    });
}
// Password Visibility Toggle
const passwordToggles = document.querySelectorAll('.password-toggle');

passwordToggles.forEach(toggle => {
    toggle.addEventListener('click', function () {
        const targetId = this.getAttribute('data-target');
        const passwordInput = document.getElementById(targetId);

        if (passwordInput.type === 'password') {
            passwordInput.type = 'text';
            this.classList.remove('bx-hide');
            this.classList.add('bx-show');
        } else {
            passwordInput.type = 'password';
            this.classList.remove('bx-show');
            this.classList.add('bx-hide');
        }
    });
});
