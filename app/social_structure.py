"""Photo slots and order from the operator's Post_Structure PowerPoint.

Reference filenames are examples for matching, never embedded posting assets.
"""
PORTRAIT = [
    ('Radha-Krishna', 'DSC03639'), ('Radha-Krishna', 'DSC03635'),
    ('Radha-Krishna', 'DSC03641'), ('Gaura', 'DSC03638'),
    ('Baladeva', 'DSC03643'), ('Subhadra', 'DSC03644'), ('Jagannath', 'DSC03645'),
]
LANDSCAPE = [
    ('Full altar', 'DSC03654'), ('Radha-Krishna', 'DSC03640'),
    ('Radha-Krishna', 'DSC03636'), ('Radha-Krishna', 'DSC03642'),
    ('Jagannath trio', 'DSC03646'), ('Small deity, tulasi', 'DSC03649'),
    ('Small deities', 'DSC03648'), ('Small deities', 'DSC03650'),
    ('Guru-parampara', 'DSC03647'), ('Acharya murti', 'DSC03652'),
]
FACEBOOK_ORDER = list(range(7, 11)) + list(range(7)) + list(range(11, 17))


def structure():
    return {'name': 'ISKCON daily darshan', 'slots': [
        {'index': i, 'subject': subject, 'reference': ref,
         'group': 'portrait' if i < 7 else 'landscape',
         'ratio': '3:4' if i < 7 else '4:3',
         'position': i + 1 if i < 7 else i - 6}
        for i, (subject, ref) in enumerate(PORTRAIT + LANDSCAPE)],
        'facebook_order': FACEBOOK_ORDER,
        'posts': [
            {'platform': 'instagram', 'group': 'portrait', 'count': 7, 'delivery': 'manual'},
            {'platform': 'instagram', 'group': 'landscape', 'count': 10, 'delivery': 'api'},
            {'platform': 'youtube', 'group': 'portrait', 'count': 7, 'delivery': 'manual'},
            {'platform': 'youtube', 'group': 'landscape', 'count': 10, 'delivery': 'manual'},
            {'platform': 'facebook', 'group': 'facebook', 'count': 17, 'delivery': 'api'},
        ]}
