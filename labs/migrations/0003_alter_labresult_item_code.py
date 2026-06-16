from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("labs", "0002_traceable_lab_values_and_ogtt_confirmation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="labresult",
            name="item_code",
            field=models.CharField(
                choices=[
                    ("FPG", "空腹血糖"),
                    ("OGTT_1H", "OGTT 1小时血糖"),
                    ("OGTT_2H", "OGTT 2小时血糖"),
                    ("TG", "甘油三酯"),
                    ("HDL_C", "高密度脂蛋白"),
                    ("GGT", "γ-谷氨酰转肽酶"),
                    ("ALB", "白蛋白"),
                    ("WBC", "白细胞计数"),
                    ("TSH", "促甲状腺激素"),
                    ("MONO_ABS", "单核细胞绝对值"),
                    ("CHE", "胆碱脂酶"),
                    ("ALT", "谷丙转氨酶"),
                    ("AST", "谷草转氨酶"),
                    ("RBC", "红细胞计数"),
                    ("HCT", "红细胞压积"),
                    ("APTT", "活化部分凝血酶原时间"),
                    ("CREA", "肌酐"),
                    ("ALP", "碱性磷酸酶"),
                    ("LYM_ABS", "淋巴细胞绝对值"),
                    ("UREA", "尿素"),
                    ("UA", "尿酸"),
                    ("TT", "凝血酶时间"),
                    ("FIB", "纤维蛋白原"),
                    ("HGB", "血红蛋白"),
                    ("PLT", "血小板计数"),
                    ("FT4", "游离甲状腺素"),
                    ("FT3", "游离三碘甲状腺原氨酸"),
                    ("DBIL", "直接胆红素"),
                    ("NEUT_ABS", "中性粒细胞绝对值"),
                    ("TC", "总胆固醇"),
                    ("TBIL", "总胆红素"),
                    ("TBA", "总胆汁酸"),
                    ("TP", "总蛋白"),
                ],
                max_length=40,
                verbose_name="项目编码",
            ),
        ),
    ]
