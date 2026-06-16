from django import forms


class ProfileForm(forms.Form):
    first_name = forms.CharField(label="姓名", max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    email = forms.EmailField(label="邮箱", required=False, widget=forms.EmailInput(attrs={"class": "form-control"}))
    mobile = forms.CharField(label="联系电话", max_length=30, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
