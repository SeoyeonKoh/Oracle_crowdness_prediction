#!/bin/bash
# ============================================================
# collector-server 초기 설정 스크립트
# ============================================================
# 서버(우분투 24.04)에 SSH 접속한 뒤 한 번만 실행한다.
#
# 사용법:
#   1) 이 파일을 서버로 복사 (맥북에서, 프로젝트 루트 기준):
#      scp -i ~/.ssh/collector.key scripts/setup_server.sh ubuntu@서버IP:~/
#   2) 서버에서 실행:
#      bash ~/setup_server.sh
#
# 하는 일:
#   [1] 시간대를 Asia/Seoul 로 (안 하면 러시아워 cron이 9시간 어긋남)
#   [2] 파이썬·git 설치
#   [3] 깃허브에서 코드 받기 (~/collector)
#   [4] APIkey.py 서식 생성 (키는 직접 입력해야 함)
#   [5] cron 두 줄 등록 (러시 10분 / 그 외 30분)
#
# 이 스크립트는 여러 번 실행해도 안전하다 (이미 된 항목은 건너뜀).
# ============================================================

set -e

GITHUB_REPO=""   # ← 여기에 https://github.com/아이디/저장소.git 입력. 비우면 3단계는 건너뜀

echo "===== [1/5] 시간대 설정 ====="
CURRENT_TZ=$(timedatectl show -p Timezone --value)
if [ "$CURRENT_TZ" != "Asia/Seoul" ]; then
    sudo timedatectl set-timezone Asia/Seoul
    echo "시간대를 Asia/Seoul 로 변경했습니다."
else
    echo "이미 Asia/Seoul 입니다."
fi
# 중요: cron 데몬은 시작 시점의 시간대를 계속 쓴다.
# 시간대를 바꿨으면 반드시 재시작해야 새 시간대로 예약이 돈다.
# (2026-07-26 실전에서 확인한 함정)
sudo systemctl restart cron
echo "cron 데몬을 재시작했습니다. (시간대 반영)"
echo "현재 서버 시각: $(date)"
echo ""

echo "===== [2/5] 파이썬·git 설치 ====="
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip git > /dev/null
pip3 install -q requests --break-system-packages
echo "python3: $(python3 --version) / pip 설치 완료"
echo ""

echo "===== [3/5] 코드 받기 ====="
if [ -d "$HOME/collector/.git" ]; then
    echo "~/collector 가 이미 있습니다. 최신으로 갱신합니다."
    cd "$HOME/collector" && git pull
elif [ -n "$GITHUB_REPO" ]; then
    git clone "$GITHUB_REPO" "$HOME/collector"
    echo "클론 완료: ~/collector"
else
    echo "GITHUB_REPO 가 비어 있어 클론을 건너뜁니다."
    echo "맥북에서 직접 복사하려면 (프로젝트 루트에서):"
    echo "  scp -i ~/.ssh/collector.key collectors/collect_citydata.py ubuntu@서버IP:~/collector/collectors/"
fi
# 표준 폴더 구조를 보장한다 (이미 있으면 그대로)
mkdir -p "$HOME/collector/collectors" "$HOME/collector/config" \
         "$HOME/collector/scripts" "$HOME/collector/logs" \
         "$HOME/collector/data/citydata"
# 옛 평면 구조에서 옮겨온 경우 파일을 제자리로 이동
[ -f "$HOME/collector/collect_citydata.py" ] && mv -f "$HOME/collector/collect_citydata.py" "$HOME/collector/collectors/"
[ -f "$HOME/collector/APIkey.py" ] && mv -f "$HOME/collector/APIkey.py" "$HOME/collector/config/"
[ -f "$HOME/collector/APIkey_example.py" ] && mv -f "$HOME/collector/APIkey_example.py" "$HOME/collector/config/"
[ -f "$HOME/collector/citydata.log" ] && mv -f "$HOME/collector/citydata.log" "$HOME/collector/logs/"
echo "폴더 구조 확인·정리 완료 (collectors/ config/ scripts/ logs/ data/)" 
echo ""

echo "===== [4/5] 인증키 파일 ====="
if [ -f "$HOME/collector/config/APIkey.py" ]; then
    echo "config/APIkey.py 가 이미 있습니다."
else
    cat > "$HOME/collector/config/APIkey.py" << 'EOF'
SEOUL_OPENDATA_GENERAL_KEY = "여기에키입력"
EOF
    echo "~/collector/config/APIkey.py 서식을 만들었습니다."
    echo ">>> 반드시 열어서 실제 키를 넣으세요:  nano ~/collector/config/APIkey.py"
fi
echo ""

echo "===== [5/5] cron 등록 ====="
# 옛 경로의 citydata 예약을 지우고 현재 구조 기준으로 다시 등록한다.
# 주의: grep -v 가 모든 줄을 걸러내면 종료코드 1이 나는데, set -e 아래에서
# 그대로 두면 서브셸이 중단되어 "빈 crontab" 이 설치된다. || true 로 방지.
# (2026-07-26 실전에서 확인한 버그)
(crontab -l 2>/dev/null | grep -v "citydata" || true; cat << 'EOF'
# citydata-collector
*/10 7-9,17-19 * * * cd /home/ubuntu/collector && /usr/bin/python3 collectors/collect_citydata.py >> logs/citydata.log 2>&1
*/30 0-6,10-16,20-23 * * * cd /home/ubuntu/collector && /usr/bin/python3 collectors/collect_citydata.py >> logs/citydata.log 2>&1
EOF
) | crontab -
echo "cron 을 현재 구조 기준으로 갱신했습니다:"
crontab -l | grep citydata
echo ""

echo "============================================================"
echo "설정 끝. 남은 일:"
echo "  1) nano ~/collector/config/APIkey.py   ← 실제 키 입력 (아직이면)"
echo "  2) cd ~/collector && python3 collectors/collect_citydata.py   ← 손 실행 1회로 12곳 성공 확인"
echo "  3) 다음 주기 뒤:  tail -5 ~/collector/logs/citydata.log   ← cron 자동 실행 확인"
echo "  4) 내일:  wc -l ~/collector/data/citydata/*.jsonl  ← 864줄 근처면 정상"
echo "============================================================"