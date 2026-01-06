
import re

def clean_youtube_video_id(video_id):
    if not video_id:
        return video_id
    
    # Extract ID from various YouTube URL formats
    patterns = [
        r'(?:v=|\/embed\/|\/1\/|\/v\/|youtu\.be\/|\/v=)([a-zA-Z0-9_-]{11})',
        r'(?:^|[\/|=])([a-zA-Z0-9_-]{11})(?:$|[?&])', # 11-char ID surrounded by separators
    ]
    
    for pattern in patterns:
        match = re.search(pattern, video_id)
        if match:
            return match.group(1)
    
    return video_id

test_cases = [
    "dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/embed/dQw4w9WgXcQ",
    "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=embed",
    "dQw4w9WgXcQ?rel=0",
]

for case in test_cases:
    print(f"Input: {case} -> Output: {clean_youtube_video_id(case)}")
