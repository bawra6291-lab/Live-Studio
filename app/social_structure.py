"""Photo slots and order from the operator's Post_Structure PowerPoint.

Reference filenames are examples for matching, never embedded posting assets.
"""
PORTRAIT = [
    ('Radha-Krishna · straight · full body', 'DSC03639'), ('Radha-Krishna · right · full body', 'DSC03635'),
    ('Radha-Krishna · left · full body', 'DSC03641'), ('Gaura Natraj', 'DSC03638'),
    ('Baladeva', 'DSC03643'), ('Subhadra', 'DSC03644'), ('Jagannath', 'DSC03645'),
]
LANDSCAPE = [
    ('Full altar · RGM', 'DSC03654'), ('Radha-Krishna · straight · half body', 'DSC03640'),
    ('Radha-Krishna · right · half body', 'DSC03636'), ('Radha-Krishna · left · half body', 'DSC03642'),
    ('Full altar · JBS', 'DSC03646'), ('Janardhan', 'DSC03649'),
    ('Radha Gopinath', 'DSC03648'), ('Radha Madan Mohan', 'DSC03650'),
    ('Guru-parampara', 'DSC03647'), ('Srila Prabhupada', 'DSC03652'),
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
