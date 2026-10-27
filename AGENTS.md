# このアプリの作業方針

- ユーザーは修正後の GitHub push と PythonAnywhere 本番反映を継続的に許可している。通常のリリースでは再確認せず、検証まで進める。
- データを消さないこと、いつでも戻せることを優先する。データ削除を伴う変更は避け、必要なら事前に影響を説明する。
- 毎回、本番反映前に SQLite の backup API で DB をバックアップし、本番の現在のコミットとコードのアーカイブを保存する。保存先は公開ディレクトリ外の `/home/anakoko/backups/`。新しいバックアップで古いものを上書きしない。
- コードのみの巻き戻しで済む場合は DB を上書きしない。DB 復元が必要な場合は、復元直前にも最新 DB を保存し、バックアップ取得後の入力を失わない復旧方法を検討する。
- 本番反映後は画面表示と既存データの保持を確認する。バックアップと戻し先のコミットを報告する。
- PythonAnywhere のコード配置先は `/home/anakoko/anakoko.pythonanywhere.com`、仮想環境は `/home/anakoko/.virtualenvs/anakoko.pythonanywhere.com`。
- ローカルで以前から変更されている `requirements.txt` は、意図を確認せずコミットに含めない。
