from django.core.management.base import BaseCommand
from django.db import transaction
from producer.models import Category, Subcategory, SubSubcategory


class Command(BaseCommand):
    help = 'Populate the database with hierarchical category data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing categories before populating',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing categories...')
            SubSubcategory.objects.all().delete()
            Subcategory.objects.all().delete()
            Category.objects.all().delete()

        categories_data = {
            "categories": [
                {
                    "code": "FA",
                    "name": "Fashion & Apparel",
                    "subcategories": [
                        {
                            "code": "FA_CL",
                            "name": "Clothing",
                            "sub_subcategories": [
                                {"code": "FA_CL_MW", "name": "Men's Wear"},
                                {"code": "FA_CL_WW", "name": "Women's Wear"},
                                {"code": "FA_CL_KW", "name": "Kids' Wear"},
                                {"code": "FA_CL_UW", "name": "Underwear & Innerwear"},
                                {"code": "FA_CL_SW", "name": "Sleepwear & Loungewear"},
                                {"code": "FA_CL_SP", "name": "Sportswear"},
                                {"code": "FA_CL_FW", "name": "Formal Wear"},
                                {"code": "FA_CL_TW", "name": "Traditional Wear"}
                            ]
                        },
                        {
                            "code": "FA_FW",
                            "name": "Footwear",
                            "sub_subcategories": [
                                {"code": "FA_FW_CS", "name": "Casual Shoes"},
                                {"code": "FA_FW_FS", "name": "Formal Shoes"},
                                {"code": "FA_FW_SS", "name": "Sports Shoes"},
                                {"code": "FA_FW_SL", "name": "Sandals & Slippers"},
                                {"code": "FA_FW_BT", "name": "Boots"},
                                {"code": "FA_FW_HH", "name": "High Heels"},
                                {"code": "FA_FW_FL", "name": "Flats"},
                                {"code": "FA_FW_SK", "name": "Sneakers"}
                            ]
                        },
                        {
                            "code": "FA_AC",
                            "name": "Accessories",
                            "sub_subcategories": [
                                {"code": "FA_AC_BG", "name": "Bags & Handbags"},
                                {"code": "FA_AC_JW", "name": "Jewelry & Watches"},
                                {"code": "FA_AC_HL", "name": "Hats & Headwear"},
                                {"code": "FA_AC_BL", "name": "Belts & Wallets"},
                                {"code": "FA_AC_EY", "name": "Eyewear"},
                                {"code": "FA_AC_SC", "name": "Scarves & Ties"},
                                {"code": "FA_AC_GL", "name": "Gloves"},
                                {"code": "FA_AC_UM", "name": "Umbrellas"}
                            ]
                        }
                    ]
                },
                {
                    "code": "EG",
                    "name": "Electronics & Gadgets",
                    "subcategories": [
                        {
                            "code": "EG_MB",
                            "name": "Mobile & Computing",
                            "sub_subcategories": [
                                {"code": "EG_MB_SP", "name": "Smartphones"},
                                {"code": "EG_MB_LP", "name": "Laptops"},
                                {"code": "EG_MB_TB", "name": "Tablets"},
                                {"code": "EG_MB_DT", "name": "Desktop Computers"},
                                {"code": "EG_MB_AC", "name": "Computer Accessories"},
                                {"code": "EG_MB_WR", "name": "Wearable Technology"},
                                {"code": "EG_MB_ST", "name": "Storage Devices"},
                                {"code": "EG_MB_NW", "name": "Networking Equipment"}
                            ]
                        },
                        {
                            "code": "EG_HA",
                            "name": "Home Appliances",
                            "sub_subcategories": [
                                {"code": "EG_HA_KA", "name": "Kitchen Appliances"},
                                {"code": "EG_HA_LA", "name": "Laundry Appliances"},
                                {"code": "EG_HA_AC", "name": "Air Conditioning & Heating"},
                                {"code": "EG_HA_TV", "name": "Television & Audio"},
                                {"code": "EG_HA_SA", "name": "Small Appliances"},
                                {"code": "EG_HA_VC", "name": "Vacuum Cleaners"},
                                {"code": "EG_HA_WH", "name": "Water Heaters"},
                                {"code": "EG_HA_RF", "name": "Refrigeration"}
                            ]
                        },
                        {
                            "code": "EG_EN",
                            "name": "Entertainment & Media",
                            "sub_subcategories": [
                                {"code": "EG_EN_GM", "name": "Gaming Consoles & Games"},
                                {"code": "EG_EN_AU", "name": "Audio Systems"},
                                {"code": "EG_EN_CM", "name": "Cameras & Photography"},
                                {"code": "EG_EN_HP", "name": "Headphones & Earphones"},
                                {"code": "EG_EN_SM", "name": "Smart Home Devices"},
                                {"code": "EG_EN_DR", "name": "Drones & RC"},
                                {"code": "EG_EN_VR", "name": "VR & AR Devices"},
                                {"code": "EG_EN_ST", "name": "Streaming Devices"}
                            ]
                        }
                    ]
                },
                {
                    "code": "GE",
                    "name": "Groceries & Essentials",
                    "subcategories": [
                        {
                            "code": "GE_FD",
                            "name": "Food & Beverages",
                            "sub_subcategories": [
                                {"code": "GE_FD_FR", "name": "Fresh Produce"},
                                {"code": "GE_FD_DR", "name": "Dairy & Refrigerated"},
                                {"code": "GE_FD_PT", "name": "Pantry Staples"},
                                {"code": "GE_FD_BV", "name": "Beverages"},
                                {"code": "GE_FD_SN", "name": "Snacks & Confectionery"},
                                {"code": "GE_FD_MT", "name": "Meat & Seafood"},
                                {"code": "GE_FD_FZ", "name": "Frozen Foods"},
                                {"code": "GE_FD_OR", "name": "Organic & Health Foods"}
                            ]
                        },
                        {
                            "code": "GE_HC",
                            "name": "Household Care",
                            "sub_subcategories": [
                                {"code": "GE_HC_CL", "name": "Cleaning Supplies"},
                                {"code": "GE_HC_DT", "name": "Detergents & Fabric Care"},
                                {"code": "GE_HC_TS", "name": "Tissues & Paper Products"},
                                {"code": "GE_HC_PC", "name": "Pest Control"},
                                {"code": "GE_HC_AR", "name": "Air Fresheners"},
                                {"code": "GE_HC_DS", "name": "Dishware & Supplies"},
                                {"code": "GE_HC_ST", "name": "Storage & Organization"},
                                {"code": "GE_HC_BG", "name": "Bags & Wraps"}
                            ]
                        },
                        {
                            "code": "GE_PC",
                            "name": "Personal Care",
                            "sub_subcategories": [
                                {"code": "GE_PC_HC", "name": "Hair Care"},
                                {"code": "GE_PC_OC", "name": "Oral Care"},
                                {"code": "GE_PC_BC", "name": "Body Care & Hygiene"},
                                {"code": "GE_PC_SH", "name": "Shaving & Grooming"},
                                {"code": "GE_PC_FH", "name": "Feminine Hygiene"},
                                {"code": "GE_PC_BB", "name": "Baby Care"},
                                {"code": "GE_PC_DT", "name": "Deodorants & Perfumes"},
                                {"code": "GE_PC_FT", "name": "Foot Care"}
                            ]
                        }
                    ]
                },
                {
                    "code": "HB",
                    "name": "Health & Beauty",
                    "subcategories": [
                        {
                            "code": "HB_SK",
                            "name": "Skincare",
                            "sub_subcategories": [
                                {"code": "HB_SK_FC", "name": "Face Care"},
                                {"code": "HB_SK_BC", "name": "Body Care"},
                                {"code": "HB_SK_SC", "name": "Sun Care"},
                                {"code": "HB_SK_AS", "name": "Anti-Aging & Serums"},
                                {"code": "HB_SK_AC", "name": "Acne Treatment"},
                                {"code": "HB_SK_SN", "name": "Sensitive Skin"},
                                {"code": "HB_SK_EX", "name": "Exfoliation"},
                                {"code": "HB_SK_MZ", "name": "Moisturizers"}
                            ]
                        },
                        {
                            "code": "HB_MU",
                            "name": "Makeup & Cosmetics",
                            "sub_subcategories": [
                                {"code": "HB_MU_FC", "name": "Face Makeup"},
                                {"code": "HB_MU_EY", "name": "Eye Makeup"},
                                {"code": "HB_MU_LP", "name": "Lip Care & Color"},
                                {"code": "HB_MU_NL", "name": "Nail Care"},
                                {"code": "HB_MU_TO", "name": "Tools & Brushes"},
                                {"code": "HB_MU_PR", "name": "Primers & Setting"},
                                {"code": "HB_MU_HL", "name": "Highlighters & Contour"},
                                {"code": "HB_MU_RM", "name": "Makeup Removers"}
                            ]
                        },
                        {
                            "code": "HB_HL",
                            "name": "Health & Wellness",
                            "sub_subcategories": [
                                {"code": "HB_HL_VT", "name": "Vitamins & Supplements"},
                                {"code": "HB_HL_FM", "name": "First Aid & Medicine"},
                                {"code": "HB_HL_FT", "name": "Fitness Equipment"},
                                {"code": "HB_HL_WL", "name": "Weight Management"},
                                {"code": "HB_HL_AR", "name": "Aromatherapy"},
                                {"code": "HB_HL_HB", "name": "Herbal & Natural"},
                                {"code": "HB_HL_PT", "name": "Protein & Sports Nutrition"},
                                {"code": "HB_HL_MM", "name": "Medical Monitoring"}
                            ]
                        }
                    ]
                },
                {
                    "code": "HL",
                    "name": "Home & Living",
                    "subcategories": [
                        {
                            "code": "HL_FR",
                            "name": "Furniture",
                            "sub_subcategories": [
                                {"code": "HL_FR_LR", "name": "Living Room"},
                                {"code": "HL_FR_BR", "name": "Bedroom"},
                                {"code": "HL_FR_DR", "name": "Dining Room"},
                                {"code": "HL_FR_OF", "name": "Office Furniture"},
                                {"code": "HL_FR_OD", "name": "Outdoor Furniture"},
                                {"code": "HL_FR_KT", "name": "Kitchen Furniture"},
                                {"code": "HL_FR_ST", "name": "Storage Furniture"},
                                {"code": "HL_FR_KD", "name": "Kids Furniture"}
                            ]
                        },
                        {
                            "code": "HL_DC",
                            "name": "Home Decor",
                            "sub_subcategories": [
                                {"code": "HL_DC_WD", "name": "Wall Decor & Art"},
                                {"code": "HL_DC_LG", "name": "Lighting & Lamps"},
                                {"code": "HL_DC_RG", "name": "Rugs & Carpets"},
                                {"code": "HL_DC_CU", "name": "Curtains & Window Treatments"},
                                {"code": "HL_DC_PL", "name": "Plants & Planters"},
                                {"code": "HL_DC_CS", "name": "Cushions & Throws"},
                                {"code": "HL_DC_MR", "name": "Mirrors"},
                                {"code": "HL_DC_CL", "name": "Candles & Fragrances"}
                            ]
                        },
                        {
                            "code": "HL_KT",
                            "name": "Kitchen & Dining",
                            "sub_subcategories": [
                                {"code": "HL_KT_CW", "name": "Cookware & Bakeware"},
                                {"code": "HL_KT_TB", "name": "Tableware & Dinnerware"},
                                {"code": "HL_KT_ST", "name": "Storage & Organization"},
                                {"code": "HL_KT_GA", "name": "Gadgets & Tools"},
                                {"code": "HL_KT_LN", "name": "Linens & Textiles"},
                                {"code": "HL_KT_GL", "name": "Glassware & Drinkware"},
                                {"code": "HL_KT_KN", "name": "Knives & Cutlery"},
                                {"code": "HL_KT_AP", "name": "Small Appliances"}
                            ]
                        },
                        {
                            "code": "HL_BD",
                            "name": "Bed & Bath",
                            "sub_subcategories": [
                                {"code": "HL_BD_BD", "name": "Bedding & Sheets"},
                                {"code": "HL_BD_TW", "name": "Towels"},
                                {"code": "HL_BD_BT", "name": "Bath Accessories"},
                                {"code": "HL_BD_PL", "name": "Pillows & Cushions"},
                                {"code": "HL_BD_BL", "name": "Blankets & Comforters"},
                                {"code": "HL_BD_MT", "name": "Mattresses & Toppers"},
                                {"code": "HL_BD_SH", "name": "Shower Curtains"},
                                {"code": "HL_BD_RB", "name": "Robes & Sleepwear"}
                            ]
                        }
                    ]
                },
                {
                    "code": "TT",
                    "name": "Travel & Tourism",
                    "subcategories": [
                        {
                            "code": "TT_LG",
                            "name": "Luggage & Bags",
                            "sub_subcategories": [
                                {"code": "TT_LG_SC", "name": "Suitcases & Hard Cases"},
                                {"code": "TT_LG_BP", "name": "Backpacks & Hiking Bags"},
                                {"code": "TT_LG_TB", "name": "Travel Bags & Soft Cases"},
                                {"code": "TT_LG_DB", "name": "Duffel & Sport Bags"},
                                {"code": "TT_LG_AC", "name": "Travel Accessories"},
                                {"code": "TT_LG_CB", "name": "Carry-on Bags"},
                                {"code": "TT_LG_WB", "name": "Wheeled Bags"},
                                {"code": "TT_LG_LT", "name": "Laptop & Business Bags"}
                            ]
                        },
                        {
                            "code": "TT_OD",
                            "name": "Outdoor & Adventure",
                            "sub_subcategories": [
                                {"code": "TT_OD_CG", "name": "Camping Gear & Tents"},
                                {"code": "TT_OD_HK", "name": "Hiking & Trekking Equipment"},
                                {"code": "TT_OD_WS", "name": "Water Sports & Swimming"},
                                {"code": "TT_OD_CL", "name": "Outdoor Clothing"},
                                {"code": "TT_OD_SF", "name": "Safety & Navigation"},
                                {"code": "TT_OD_CK", "name": "Cooking & Survival"},
                                {"code": "TT_OD_BK", "name": "Biking & Cycling"},
                                {"code": "TT_OD_FS", "name": "Fishing & Hunting"}
                            ]
                        },
                        {
                            "code": "TT_TR",
                            "name": "Travel Essentials",
                            "sub_subcategories": [
                                {"code": "TT_TR_TO", "name": "Travel Organizers & Packing"},
                                {"code": "TT_TR_PC", "name": "Personal Care Travel Kits"},
                                {"code": "TT_TR_EL", "name": "Electronics & Chargers"},
                                {"code": "TT_TR_CO", "name": "Comfort & Sleep"},
                                {"code": "TT_TR_DC", "name": "Documents & Money"},
                                {"code": "TT_TR_HL", "name": "Health & Safety"},
                                {"code": "TT_TR_AD", "name": "Adapters & Converters"},
                                {"code": "TT_TR_EN", "name": "Entertainment & Books"}
                            ]
                        }
                    ]
                },
                {
                    "code": "IS",
                    "name": "Industrial Supplies",
                    "subcategories": [
                        {
                            "code": "IS_TL",
                            "name": "Tools & Equipment",
                            "sub_subcategories": [
                                {"code": "IS_TL_PT", "name": "Power Tools"},
                                {"code": "IS_TL_HT", "name": "Hand Tools"},
                                {"code": "IS_TL_MS", "name": "Measuring & Testing"},
                                {"code": "IS_TL_SF", "name": "Safety Equipment"},
                                {"code": "IS_TL_WE", "name": "Welding & Cutting"},
                                {"code": "IS_TL_CR", "name": "Construction Tools"},
                                {"code": "IS_TL_GD", "name": "Gardening & Landscaping"},
                                {"code": "IS_TL_AU", "name": "Automotive Tools"}
                            ]
                        },
                        {
                            "code": "IS_RW",
                            "name": "Raw Materials",
                            "sub_subcategories": [
                                {"code": "IS_RW_MT", "name": "Metals & Alloys"},
                                {"code": "IS_RW_PL", "name": "Plastics & Polymers"},
                                {"code": "IS_RW_CH", "name": "Chemicals & Compounds"},
                                {"code": "IS_RW_TX", "name": "Textiles & Fabrics"},
                                {"code": "IS_RW_WD", "name": "Wood & Lumber"},
                                {"code": "IS_RW_ST", "name": "Stone & Concrete"},
                                {"code": "IS_RW_GL", "name": "Glass & Ceramics"},
                                {"code": "IS_RW_RB", "name": "Rubber & Adhesives"}
                            ]
                        },
                        {
                            "code": "IS_MC",
                            "name": "Machinery & Components",
                            "sub_subcategories": [
                                {"code": "IS_MC_PR", "name": "Production Machinery"},
                                {"code": "IS_MC_EL", "name": "Electrical Components"},
                                {"code": "IS_MC_HY", "name": "Hydraulic & Pneumatic"},
                                {"code": "IS_MC_PT", "name": "Parts & Fasteners"},
                                {"code": "IS_MC_MT", "name": "Maintenance Supplies"},
                                {"code": "IS_MC_BR", "name": "Bearings & Motion"},
                                {"code": "IS_MC_FL", "name": "Fluid Handling"},
                                {"code": "IS_MC_CT", "name": "Control Systems"}
                            ]
                        }
                    ]
                },
                {
                    "code": "AU",
                    "name": "Automotive",
                    "subcategories": [
                        {
                            "code": "AU_PT",
                            "name": "Parts & Components",
                            "sub_subcategories": [
                                {"code": "AU_PT_EN", "name": "Engine Parts"},
                                {"code": "AU_PT_BR", "name": "Brakes & Suspension"},
                                {"code": "AU_PT_EL", "name": "Electrical & Lighting"},
                                {"code": "AU_PT_BD", "name": "Body & Exterior"},
                                {"code": "AU_PT_IN", "name": "Interior & Comfort"},
                                {"code": "AU_PT_TR", "name": "Transmission & Drivetrain"},
                                {"code": "AU_PT_FL", "name": "Fluids & Chemicals"},
                                {"code": "AU_PT_TI", "name": "Tires & Wheels"}
                            ]
                        },
                        {
                            "code": "AU_AC",
                            "name": "Accessories",
                            "sub_subcategories": [
                                {"code": "AU_AC_ET", "name": "Electronics & Tech"},
                                {"code": "AU_AC_CR", "name": "Car Care & Cleaning"},
                                {"code": "AU_AC_SF", "name": "Safety & Security"},
                                {"code": "AU_AC_CO", "name": "Comfort & Convenience"},
                                {"code": "AU_AC_ST", "name": "Storage & Organization"},
                                {"code": "AU_AC_SP", "name": "Sports & Recreation"},
                                {"code": "AU_AC_DG", "name": "Diagnostic Tools"},
                                {"code": "AU_AC_EM", "name": "Emergency Kits"}
                            ]
                        },
                        {
                            "code": "AU_MO",
                            "name": "Motorcycle & ATV",
                            "sub_subcategories": [
                                {"code": "AU_MO_PT", "name": "Motorcycle Parts"},
                                {"code": "AU_MO_GR", "name": "Riding Gear & Apparel"},
                                {"code": "AU_MO_AC", "name": "Accessories & Storage"},
                                {"code": "AU_MO_MN", "name": "Maintenance & Tools"},
                                {"code": "AU_MO_SF", "name": "Safety Equipment"},
                                {"code": "AU_MO_AT", "name": "ATV & Off-road"},
                                {"code": "AU_MO_TI", "name": "Tires & Wheels"},
                                {"code": "AU_MO_EL", "name": "Electronics"}
                            ]
                        }
                    ]
                },
                {
                    "code": "SP",
                    "name": "Sports & Fitness",
                    "subcategories": [
                        {
                            "code": "SP_FT",
                            "name": "Fitness Equipment",
                            "sub_subcategories": [
                                {"code": "SP_FT_CD", "name": "Cardio Equipment"},
                                {"code": "SP_FT_ST", "name": "Strength Training"},
                                {"code": "SP_FT_YG", "name": "Yoga & Pilates"},
                                {"code": "SP_FT_FW", "name": "Free Weights"},
                                {"code": "SP_FT_AC", "name": "Fitness Accessories"},
                                {"code": "SP_FT_WR", "name": "Wearable Fitness Tech"},
                                {"code": "SP_FT_MT", "name": "Exercise Mats"},
                                {"code": "SP_FT_HM", "name": "Home Gym Equipment"}
                            ]
                        },
                        {
                            "code": "SP_OT",
                            "name": "Outdoor Sports",
                            "sub_subcategories": [
                                {"code": "SP_OT_BK", "name": "Biking & Cycling"},
                                {"code": "SP_OT_RN", "name": "Running & Athletics"},
                                {"code": "SP_OT_SW", "name": "Swimming & Water Sports"},
                                {"code": "SP_OT_HK", "name": "Hiking & Climbing"},
                                {"code": "SP_OT_SK", "name": "Skiing & Snow Sports"},
                                {"code": "SP_OT_FS", "name": "Fishing & Hunting"},
                                {"code": "SP_OT_GL", "name": "Golf"},
                                {"code": "SP_OT_TN", "name": "Tennis & Racquet Sports"}
                            ]
                        },
                        {
                            "code": "SP_TM",
                            "name": "Team Sports",
                            "sub_subcategories": [
                                {"code": "SP_TM_FB", "name": "Football & Soccer"},
                                {"code": "SP_TM_BK", "name": "Basketball"},
                                {"code": "SP_TM_BB", "name": "Baseball & Softball"},
                                {"code": "SP_TM_VB", "name": "Volleyball"},
                                {"code": "SP_TM_HY", "name": "Hockey"},
                                {"code": "SP_TM_CR", "name": "Cricket"},
                                {"code": "SP_TM_RG", "name": "Rugby"},
                                {"code": "SP_TM_BD", "name": "Badminton"}
                            ]
                        }
                    ]
                },
                {
                    "code": "BK",
                    "name": "Books & Media",
                    "subcategories": [
                        {
                            "code": "BK_BK",
                            "name": "Books",
                            "sub_subcategories": [
                                {"code": "BK_BK_FC", "name": "Fiction & Literature"},
                                {"code": "BK_BK_NF", "name": "Non-Fiction"},
                                {"code": "BK_BK_ED", "name": "Educational & Academic"},
                                {"code": "BK_BK_CH", "name": "Children's Books"},
                                {"code": "BK_BK_RF", "name": "Reference & Dictionaries"},
                                {"code": "BK_BK_RL", "name": "Religion & Spirituality"},
                                {"code": "BK_BK_HB", "name": "Health & Self-Help"},
                                {"code": "BK_BK_BG", "name": "Biography & Memoir"}
                            ]
                        },
                        {
                            "code": "BK_MD",
                            "name": "Digital Media",
                            "sub_subcategories": [
                                {"code": "BK_MD_MV", "name": "Movies & TV Shows"},
                                {"code": "BK_MD_MS", "name": "Music & Audio"},
                                {"code": "BK_MD_GM", "name": "Video Games"},
                                {"code": "BK_MD_SW", "name": "Software"},
                                {"code": "BK_MD_AB", "name": "Audiobooks"},
                                {"code": "BK_MD_EB", "name": "E-books"},
                                {"code": "BK_MD_PC", "name": "Podcasts"},
                                {"code": "BK_MD_OC", "name": "Online Courses"}
                            ]
                        },
                        {
                            "code": "BK_ST",
                            "name": "Stationery & Office",
                            "sub_subcategories": [
                                {"code": "BK_ST_WR", "name": "Writing Instruments"},
                                {"code": "BK_ST_PP", "name": "Paper & Notebooks"},
                                {"code": "BK_ST_OR", "name": "Organization & Filing"},
                                {"code": "BK_ST_AR", "name": "Art & Craft Supplies"},
                                {"code": "BK_ST_OF", "name": "Office Equipment"},
                                {"code": "BK_ST_SC", "name": "School Supplies"},
                                {"code": "BK_ST_CL", "name": "Calendars & Planners"},
                                {"code": "BK_ST_GF", "name": "Gifts & Cards"}
                            ]
                        }
                    ]
                },
                {
                    "code": "PB",
                    "name": "Pet & Baby Care",
                    "subcategories": [
                        {
                            "code": "PB_PT",
                            "name": "Pet Supplies",
                            "sub_subcategories": [
                                {"code": "PB_PT_FD", "name": "Pet Food & Treats"},
                                {"code": "PB_PT_TY", "name": "Toys & Entertainment"},
                                {"code": "PB_PT_CR", "name": "Carriers & Travel"},
                                {"code": "PB_PT_BD", "name": "Beds & Furniture"},
                                {"code": "PB_PT_GR", "name": "Grooming & Health"},
                                {"code": "PB_PT_CL", "name": "Collars & Leashes"},
                                {"code": "PB_PT_AQ", "name": "Aquarium & Fish"},
                                {"code": "PB_PT_SM", "name": "Small Animals & Birds"}
                            ]
                        },
                        {
                            "code": "PB_BB",
                            "name": "Baby Care",
                            "sub_subcategories": [
                                {"code": "PB_BB_FD", "name": "Baby Food & Formula"},
                                {"code": "PB_BB_DP", "name": "Diapers & Wipes"},
                                {"code": "PB_BB_CL", "name": "Baby Clothing"},
                                {"code": "PB_BB_TY", "name": "Toys & Development"},
                                {"code": "PB_BB_FR", "name": "Furniture & Nursery"},
                                {"code": "PB_BB_ST", "name": "Strollers & Car Seats"},
                                {"code": "PB_BB_FE", "name": "Feeding & Bottles"},
                                {"code": "PB_BB_BT", "name": "Bath & Skincare"}
                            ]
                        },
                        {
                            "code": "PB_MT",
                            "name": "Maternity",
                            "sub_subcategories": [
                                {"code": "PB_MT_CL", "name": "Maternity Clothing"},
                                {"code": "PB_MT_NR", "name": "Nursing & Breastfeeding"},
                                {"code": "PB_MT_HT", "name": "Health & Wellness"},
                                {"code": "PB_MT_SP", "name": "Support & Comfort"},
                                {"code": "PB_MT_VT", "name": "Vitamins & Supplements"},
                                {"code": "PB_MT_EX", "name": "Exercise & Fitness"},
                                {"code": "PB_MT_BK", "name": "Books & Education"},
                                {"code": "PB_MT_AC", "name": "Accessories"}
                            ]
                        }
                    ]
                },
                {
                    "code": "GD",
                    "name": "Garden & Outdoor",
                    "subcategories": [
                        {
                            "code": "GD_GR",
                            "name": "Gardening",
                            "sub_subcategories": [
                                {"code": "GD_GR_PL", "name": "Plants & Seeds"},
                                {"code": "GD_GR_TL", "name": "Tools & Equipment"},
                                {"code": "GD_GR_FL", "name": "Fertilizers & Soil"},
                                {"code": "GD_GR_PT", "name": "Pots & Planters"},
                                {"code": "GD_GR_IR", "name": "Irrigation & Watering"},
                                {"code": "GD_GR_PS", "name": "Pest Control"},
                                {"code": "GD_GR_GH", "name": "Greenhouses & Structures"},
                                {"code": "GD_GR_DC", "name": "Garden Decor"}
                            ]
                        },
                        {
                            "code": "GD_OD",
                            "name": "Outdoor Living",
                            "sub_subcategories": [
                                {"code": "GD_OD_FR", "name": "Outdoor Furniture"},
                                {"code": "GD_OD_GR", "name": "Grilling & BBQ"},
                                {"code": "GD_OD_LG", "name": "Outdoor Lighting"},
                                {"code": "GD_OD_UM", "name": "Umbrellas & Shade"},
                                {"code": "GD_OD_HT", "name": "Heating & Cooling"},
                                {"code": "GD_OD_DC", "name": "Outdoor Decor"},
                                {"code": "GD_OD_PL", "name": "Pools & Water Features"},
                                {"code": "GD_OD_ST", "name": "Storage & Sheds"}
                            ]
                        },
                        {
                            "code": "GD_LS",
                            "name": "Landscaping",
                            "sub_subcategories": [
                                {"code": "GD_LS_ST", "name": "Stones & Gravel"},
                                {"code": "GD_LS_ML", "name": "Mulch & Bark"},
                                {"code": "GD_LS_FN", "name": "Fencing & Borders"},
                                {"code": "GD_LS_PV", "name": "Pavers & Walkways"},
                                {"code": "GD_LS_RT", "name": "Retaining Walls"},
                                {"code": "GD_LS_DR", "name": "Drainage Solutions"},
                                {"code": "GD_LS_TF", "name": "Turf & Grass"},
                                {"code": "GD_LS_TL", "name": "Landscape Tools"}
                            ]
                        }
                    ]
                },
                {
                    "code": "FD",
                    "name": "Food & Beverages",
                    "subcategories": [
                        {
                            "code": "FD_FR",
                            "name": "Fresh Food",
                            "sub_subcategories": [
                                {"code": "FD_FR_VG", "name": "Vegetables"},
                                {"code": "FD_FR_FR", "name": "Fruits"},
                                {"code": "FD_FR_MT", "name": "Meat & Poultry"},
                                {"code": "FD_FR_SF", "name": "Seafood"},
                                {"code": "FD_FR_DR", "name": "Dairy Products"},
                                {"code": "FD_FR_BK", "name": "Bakery & Bread"},
                                {"code": "FD_FR_DL", "name": "Deli & Prepared"},
                                {"code": "FD_FR_OR", "name": "Organic & Natural"}
                            ]
                        },
                        {
                            "code": "FD_PK",
                            "name": "Packaged Food",
                            "sub_subcategories": [
                                {"code": "FD_PK_CN", "name": "Canned & Jarred"},
                                {"code": "FD_PK_FZ", "name": "Frozen Foods"},
                                {"code": "FD_PK_SN", "name": "Snacks & Chips"},
                                {"code": "FD_PK_CF", "name": "Confectionery & Sweets"},
                                {"code": "FD_PK_CS", "name": "Cereals & Breakfast"},
                                {"code": "FD_PK_PS", "name": "Pasta & Rice"},
                                {"code": "FD_PK_SP", "name": "Spices & Seasonings"},
                                {"code": "FD_PK_SS", "name": "Sauces & Condiments"}
                            ]
                        },
                        {
                            "code": "FD_BV",
                            "name": "Beverages",
                            "sub_subcategories": [
                                {"code": "FD_BV_WT", "name": "Water & Soft Drinks"},
                                {"code": "FD_BV_JU", "name": "Juices & Smoothies"},
                                {"code": "FD_BV_CF", "name": "Coffee & Tea"},
                                {"code": "FD_BV_AL", "name": "Alcoholic Beverages"},
                                {"code": "FD_BV_EN", "name": "Energy & Sports Drinks"},
                                {"code": "FD_BV_ML", "name": "Milk & Dairy Drinks"},
                                {"code": "FD_BV_HT", "name": "Health & Wellness Drinks"},
                                {"code": "FD_BV_SP", "name": "Specialty & International"}
                            ]
                        }
                    ]
                },
                {
                    "code": "OT",
                    "name": "Other",
                    "subcategories": [
                        {
                            "code": "OT_SP",
                            "name": "Specialty Items",
                            "sub_subcategories": [
                                {"code": "OT_SP_CO", "name": "Collectibles & Antiques"},
                                {"code": "OT_SP_AR", "name": "Art & Handcrafts"},
                                {"code": "OT_SP_MU", "name": "Musical Instruments"},
                                {"code": "OT_SP_HD", "name": "Hobbies & DIY"},
                                {"code": "OT_SP_MT", "name": "Military & Tactical"},
                                {"code": "OT_SP_RL", "name": "Religious Items"},
                                {"code": "OT_SP_WD", "name": "Wedding & Events"},
                                {"code": "OT_SP_PT", "name": "Party Supplies"}
                            ]
                        },
                        {
                            "code": "OT_SV",
                            "name": "Services",
                            "sub_subcategories": [
                                {"code": "OT_SV_PR", "name": "Professional Services"},
                                {"code": "OT_SV_DG", "name": "Digital Services"},
                                {"code": "OT_SV_CN", "name": "Consultation & Coaching"},
                                {"code": "OT_SV_MT", "name": "Maintenance & Repair"},
                                {"code": "OT_SV_ED", "name": "Education & Training"},
                                {"code": "OT_SV_HL", "name": "Health & Wellness Services"},
                                {"code": "OT_SV_EV", "name": "Event Services"},
                                {"code": "OT_SV_TR", "name": "Transportation Services"}
                            ]
                        },
                        {
                            "code": "OT_MS",
                            "name": "Miscellaneous",
                            "sub_subcategories": [
                                {"code": "OT_MS_GF", "name": "Gifts & Novelties"},
                                {"code": "OT_MS_SN", "name": "Seasonal & Holiday"},
                                {"code": "OT_MS_PR", "name": "Promotional Items"},
                                {"code": "OT_MS_UN", "name": "Uncategorized"},
                                {"code": "OT_MS_CS", "name": "Custom & Personalized"},
                                {"code": "OT_MS_VT", "name": "Vintage & Retro"},
                                {"code": "OT_MS_LX", "name": "Luxury Items"},
                                {"code": "OT_MS_EC", "name": "Eco-Friendly Products"}
                            ]
                        }
                    ]
                }
            ]
        }

        with transaction.atomic():
            self.stdout.write('Creating categories...')
            
            for category_data in categories_data['categories']:
                category, created = Category.objects.get_or_create(
                    code=category_data['code'],
                    defaults={'name': category_data['name']}
                )
                if created:
                    self.stdout.write(f'  Created category: {category.name}')
                else:
                    self.stdout.write(f'  Category already exists: {category.name}')

                for subcategory_data in category_data['subcategories']:
                    subcategory, created = Subcategory.objects.get_or_create(
                        code=subcategory_data['code'],
                        defaults={
                            'name': subcategory_data['name'],
                            'category': category
                        }
                    )
                    if created:
                        self.stdout.write(f'    Created subcategory: {subcategory.name}')

                    for sub_subcategory_data in subcategory_data['sub_subcategories']:
                        sub_subcategory, created = SubSubcategory.objects.get_or_create(
                            code=sub_subcategory_data['code'],
                            defaults={
                                'name': sub_subcategory_data['name'],
                                'subcategory': subcategory
                            }
                        )
                        if created:
                            self.stdout.write(f'      Created sub-subcategory: {sub_subcategory.name}')

        self.stdout.write(
            self.style.SUCCESS('Successfully populated categories!')
        )