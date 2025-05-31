from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, IntegerField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, NumberRange, Optional, Regexp
from models import User
from flask_login import current_user
from flask import session
from translations import translations

def get_translation(key):
    """Get translation for the current language"""
    language = session.get('language', 'fa')
    return translations[language].get(key, translations['fa'].get(key, key))

class LoginForm(FlaskForm):
    phone_number = StringField('Phone Number', validators=[
        DataRequired(),
        Regexp(r'^(\+98|0)?9\d{9}$', message='Please enter a valid Iranian phone number starting with +98 or 0 followed by 9 and 9 digits')
    ])
    verification_code = StringField('Verification Code', validators=[
        DataRequired(),
        Regexp(r'^\d{6}$', message='Verification code must be exactly 6 digits')
    ])
    submit = SubmitField('Continue')
    step = 1  # Default step

    def __init__(self, *args, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)
        self.step = session.get('login_step', 1)

    def validate(self, extra_validators=None):
        from flask import session
        self.step = session.get('login_step', 1)
        if self.step == 1:
            # Only validate phone number
            if not self.phone_number.data or len(self.phone_number.data) < 10:
                self.phone_number.errors.append('شماره تلفن معتبر نیست.')
                return False
            return True
        else:
            # Only validate verification code
            if not self.verification_code.data or len(self.verification_code.data) != 6:
                self.verification_code.errors.append('کد تایید باید دقیقاً 6 رقم باشد.')
                return False
            return True

class RegisterForm(FlaskForm):
    password = PasswordField('رمز عبور', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('تکرار رمز عبور', validators=[DataRequired(), EqualTo('password')])
    phone_number = StringField('شماره تلفن', validators=[DataRequired(), Length(min=10, max=20)])
    submit = SubmitField('ادامه')

    def validate_phone_number(self, phone_number):
        formatted_number = User.format_phone_number(phone_number.data)
        user = User.query.filter_by(phone_number=formatted_number).first()
        if user is not None:
            raise ValidationError('این شماره تلفن قبلاً ثبت شده است.')
        phone_number.data = formatted_number
        self.username = formatted_number

class RegisterAddressForm(FlaskForm):
    street = StringField('آدرس', validators=[DataRequired(), Length(max=200)])
    tag = StringField('برچسب (مثال: خانه، محل کار)', validators=[DataRequired(), Length(max=50)])
    building_unit_number = StringField('شماره ساختمان/واحد', validators=[Optional(), Length(max=50)])
    description = TextAreaField('توضیحات (اختیاری)', validators=[Optional(), Length(max=500)])
    submit = SubmitField('ذخیره آدرس')

class ProfileForm(FlaskForm):
    username = StringField('نام کاربری', validators=[Optional(), Length(min=4, max=20)])
    email = StringField('ایمیل', validators=[Optional(), Email()])
    profile_picture = FileField('تصویر پروفایل', validators=[
        FileAllowed(['jpg', 'png', 'jpeg'], 'فقط تصاویر!')
    ])
    identity_card = FileField('کارت شناسایی', validators=[
        FileAllowed(['jpg', 'png', 'jpeg', 'pdf'], 'فقط تصاویر یا PDF!')
    ])
    phone_number = StringField('شماره تلفن', validators=[DataRequired(), Length(min=10, max=20)], render_kw={'readonly': True})
    submit = SubmitField('بروزرسانی پروفایل')

    def validate_phone_number(self, phone_number):
        formatted_number = User.format_phone_number(phone_number.data)
        user = User.query.filter_by(phone_number=formatted_number).first()
        if user is not None and user != current_user:
            raise ValidationError('این شماره تلفن قبلاً ثبت شده است.')
        phone_number.data = formatted_number

    def validate_email(self, email):
        if email.data and email.data.strip():
            user = User.query.filter_by(email=email.data).first()
            if user is not None and user != current_user:
                raise ValidationError('لطفاً از یک آدرس ایمیل دیگر استفاده کنید.')

class AddressForm(FlaskForm):
    street = StringField('آدرس', validators=[DataRequired(), Length(max=200)])
    tag = StringField('برچسب (مثال: خانه، محل کار)', validators=[DataRequired(), Length(max=50)])
    building_unit_number = StringField('شماره ساختمان/واحد', validators=[Optional(), Length(max=50)])
    description = TextAreaField('توضیحات (اختیاری)', validators=[Optional(), Length(max=500)])
    is_default = BooleanField('تنظیم به عنوان آدرس پیش‌فرض')
    submit = SubmitField('ذخیره آدرس')

class PasswordResetForm(FlaskForm):
    current_password = PasswordField('رمز عبور فعلی', validators=[DataRequired()])
    new_password = PasswordField('رمز عبور جدید', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('تکرار رمز عبور جدید', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('تغییر رمز عبور')

    def validate_current_password(self, current_password):
        if not current_user.check_password(current_password.data):
            raise ValidationError('رمز عبور فعلی اشتباه است.') 