from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, IntegerField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, NumberRange, Optional
from models import User
from flask_login import current_user
from flask import session
from translations import translations

def get_translation(key):
    """Get translation for the current language"""
    language = session.get('language', 'fa')
    return translations[language].get(key, translations['fa'].get(key, key))

class LoginForm(FlaskForm):
    phone_number = StringField('شماره تلفن', validators=[DataRequired(), Length(min=10, max=20)])
    password = PasswordField('رمز عبور', validators=[DataRequired()])
    remember_me = BooleanField('مرا به خاطر بسپار')
    submit = SubmitField('ورود')

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