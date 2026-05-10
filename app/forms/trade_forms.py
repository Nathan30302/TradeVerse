"""
Trade Forms
Forms for trade planning and review - Redesigned for Before/After workflow
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, FloatField, IntegerField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange


class TradePlanBeforeForm(FlaskForm):
    """Form for BEFORE trade planning - Phase 1"""
    
    # Basic Trade Info
    symbol = StringField(
        'Symbol / Pair',
        validators=[DataRequired(message="Please enter the trading symbol")],
        default='XAUUSD'
    )
    
    direction = SelectField(
        'Direction',
        choices=[
            ('', 'Select direction...'),
            ('BUY', '📈 Buy (Long)'),
            ('SELL', '📉 Sell (Short)')
        ],
        validators=[DataRequired(message="Please select direction")]
    )
    
    # Planned Levels
    planned_entry = FloatField(
        'Planned Entry Price',
        validators=[DataRequired(message="Please enter planned entry price")]
    )
    
    planned_stop_loss = FloatField(
        'Planned Stop Loss',
        validators=[DataRequired(message="Please enter planned stop loss")]
    )
    
    planned_take_profit = FloatField(
        'Planned Take Profit',
        validators=[DataRequired(message="Please enter planned take profit")]
    )
    
    planned_lot_size = FloatField(
        'Planned Lot Size',
        validators=[
            DataRequired(message="Please enter lot size"),
            NumberRange(min=0.01, max=100, message="Lot size must be between 0.01 and 100")
        ],
        default=0.01
    )
    
    # Strategy
    strategy = SelectField(
        'Strategy Used',
        choices=[
            ('', 'Select strategy...'),
            ('Breakout', '💥 Breakout'),
            ('Retest', '🔄 Retest'),
            ('Trend Continuation', '📈 Trend Continuation'),
            ('Reversal', '🔃 Reversal'),
            ('SMC', '🎯 Smart Money Concepts (SMC)'),
            ('Scalping', '⚡ Scalping'),
            ('Swing', '🌊 Swing Trading'),
            ('Supply/Demand', '📊 Supply & Demand'),
            ('Liquidity Grab', '💧 Liquidity Grab'),
            ('Fair Value Gap', '📉 Fair Value Gap'),
            ('Other', '📝 Other')
        ],
        validators=[DataRequired(message="Please select a strategy")]
    )
    
    # Checklist toggles
    market_structure_confirmed = BooleanField('Market structure confirmed', default=False)
    liquidity_taken = BooleanField('Liquidity taken', default=False)
    confirmation_candle_formed = BooleanField('Confirmation candle formed', default=False)
    session_aligned = BooleanField('Session aligned', default=False)
    
    # Screenshot
    screenshot_before = FileField(
        'Before Screenshot (Chart Analysis)',
        validators=[
            FileAllowed(['png', 'jpg', 'jpeg', 'gif', 'webp', 'heic'], 'Images only!')
        ]
    )
    
    # Notes
    pre_trade_notes = TextAreaField(
        'Trade Plan Notes',
        validators=[Optional()]
    )
    
    submit = SubmitField('Save Trade Plan')


class TradePlanAfterForm(FlaskForm):
    """Form for AFTER trade execution - Phase 2"""
    
    # Actual Execution
    actual_entry = FloatField(
        'Actual Entry Price',
        validators=[DataRequired(message="Please enter actual entry price")]
    )
    
    actual_exit = FloatField(
        'Actual Exit Price',
        validators=[DataRequired(message="Please enter actual exit price")]
    )
    
    # Emotion selector with emojis
    emotion_after = SelectField(
        'How did you feel during/after the trade?',
        choices=[
            ('', 'Select emotion...'),
            ('Calm', '😌 Calm'),
            ('Confident', '😎 Confident'),
            ('Excited', '🤩 Excited'),
            ('Anxious', '😰 Anxious'),
            ('Fearful', '😨 Fearful'),
            ('Greedy', '🤑 Greedy'),
            ('FOMO', '😱 FOMO'),
            ('Revenge', '😤 Revenge Trading'),
            ('Frustrated', '😠 Frustrated'),
            ('Relieved', '😮‍💨 Relieved'),
            ('Regretful', '😔 Regretful'),
            ('Neutral', '😐 Neutral')
        ],
        validators=[DataRequired(message="Please select how you felt")]
    )
    
    # Trade Grade
    trade_grade = SelectField(
        'Trade Grade',
        choices=[
            ('', 'Grade your trade...'),
            ('A', '🏆 A - Perfect execution'),
            ('B', '👍 B - Good trade, minor issues'),
            ('C', '👌 C - Acceptable, room for improvement'),
            ('D', '👎 D - Poor execution, learn from it')
        ],
        validators=[DataRequired(message="Please grade your trade")]
    )
    
    # Screenshot
    screenshot_after = FileField(
        'After Screenshot (Result)',
        validators=[
            FileAllowed(['png', 'jpg', 'jpeg', 'gif', 'webp', 'heic'], 'Images only!')
        ]
    )
    
    # Reflection
    reflection_notes = TextAreaField(
        'Reflection Notes',
        validators=[Optional()],
        description='What did you learn? What would you do differently?'
    )
    
    submit = SubmitField('Complete Review')


# Legacy forms for backward compatibility
class TradePlanForm(FlaskForm):
    """Form for BEFORE trade planning (Legacy)"""
    
    # Market Analysis
    market_bias = SelectField(
        'Market Bias',
        choices=[
            ('', 'Select bias...'),
            ('Bullish', '📈 Bullish'),
            ('Bearish', '📉 Bearish'),
            ('Neutral', '➡️ Neutral')
        ],
        validators=[DataRequired(message="Please select market bias")]
    )
    
    setup_type = SelectField(
        'Setup Type',
        choices=[
            ('', 'Select setup...'),
            ('Support/Resistance', 'Support/Resistance'),
            ('Trendline Break', 'Trendline Break'),
            ('Supply/Demand Zone', 'Supply/Demand Zone'),
            ('Liquidity Grab', 'Liquidity Grab'),
            ('Fair Value Gap', 'Fair Value Gap'),
            ('Head & Shoulders', 'Head & Shoulders'),
            ('Double Top/Bottom', 'Double Top/Bottom'),
            ('Triangle Pattern', 'Triangle Pattern'),
            ('Moving Average Crossover', 'Moving Average Crossover'),
            ('Other', 'Other')
        ],
        validators=[DataRequired(message="Please select setup type")]
    )
    
    confluence_score = IntegerField(
        'Confluence Score (0-10)',
        validators=[
            DataRequired(message="Please rate your confluence"),
            NumberRange(min=0, max=10, message="Score must be between 0 and 10")
        ]
    )
    
    # Planned Levels
    planned_entry = FloatField(
        'Planned Entry Price',
        validators=[DataRequired(message="Please enter planned entry price")]
    )
    
    planned_stop_loss = FloatField(
        'Planned Stop Loss',
        validators=[DataRequired(message="Please enter planned stop loss")]
    )
    
    planned_take_profit = FloatField(
        'Planned Take Profit',
        validators=[DataRequired(message="Please enter planned take profit")]
    )
    
    # Risk Management
    planned_risk_percentage = FloatField(
        'Risk % of Account',
        validators=[
            DataRequired(message="Please enter risk percentage"),
            NumberRange(min=0.1, max=10, message="Risk should be between 0.1% and 10%")
        ]
    )
    
    # Psychology
    emotion_before = SelectField(
        'How do you feel RIGHT NOW?',
        choices=[
            ('', 'Select emotion...'),
            ('Confident', '😎 Confident'),
            ('Calm & Focused', '🧘 Calm & Focused'),
            ('Excited', '🤩 Excited'),
            ('Nervous', '😰 Nervous'),
            ('Anxious', '😟 Anxious'),
            ('FOMO', '😱 FOMO'),
            ('Revenge Trading', '😤 Revenge Trading'),
            ('Greedy', '🤑 Greedy'),
            ('Tired', '😴 Tired'),
            ('Bored', '😑 Bored')
        ],
        validators=[DataRequired(message="Please select your emotion")]
    )
    
    emotion_intensity_before = IntegerField(
        'Emotion Intensity (1-10)',
        validators=[
            DataRequired(message="Rate your emotion intensity"),
            NumberRange(min=1, max=10, message="Intensity must be between 1 and 10")
        ]
    )
    
    # Screenshot
    screenshot_before = FileField(
        'Upload Chart Screenshot (Before)',
        validators=[
            FileAllowed(['png', 'jpg', 'jpeg', 'gif', 'webp', 'heic'], 'Images only!')
        ]
    )
    
    # Notes
    pre_trade_notes = TextAreaField(
        'Pre-Trade Notes',
        validators=[DataRequired(message="Please explain your trade plan")]
    )
    
    key_levels = TextAreaField('Key Support/Resistance Levels', validators=[Optional()])
    
    trade_hypothesis = TextAreaField(
        'What do you expect to happen?',
        validators=[Optional()]
    )
    
    submit = SubmitField('Save Trade Plan')


class TradeReviewForm(FlaskForm):
    """Form for AFTER trade review (Legacy)"""
    
    # Execution
    execution_notes = TextAreaField(
        'What actually happened?',
        validators=[DataRequired(message="Please describe what happened")]
    )
    
    trade_result = SelectField(
        'Trade Result',
        choices=[
            ('', 'Select result...'),
            ('Win', '✅ Win'),
            ('Loss', '❌ Loss'),
            ('Break Even', '➖ Break Even')
        ],
        validators=[DataRequired(message="Please select trade result")]
    )
    
    # Plan Adherence
    followed_entry = BooleanField('I entered at planned price', default=True)
    followed_stop_loss = BooleanField('I respected my stop loss', default=True)
    followed_take_profit = BooleanField('I took profit as planned', default=True)
    moved_stop_loss = BooleanField('I moved my stop loss (Red Flag!)', default=False)
    
    # Mistakes and Lessons
    mistakes_made = TextAreaField('What mistakes did I make?', validators=[Optional()])
    lessons_learned = TextAreaField('What did I learn?', validators=[Optional()])
    what_went_well = TextAreaField('What went well?', validators=[Optional()])
    what_went_wrong = TextAreaField('What went wrong?', validators=[Optional()])
    
    # Psychology After
    emotion_after = SelectField(
        'How do you feel NOW?',
        choices=[
            ('', 'Select emotion...'),
            ('Happy', '😊 Happy'),
            ('Satisfied', '😌 Satisfied'),
            ('Disappointed', '😞 Disappointed'),
            ('Frustrated', '😠 Frustrated'),
            ('Angry', '😡 Angry'),
            ('Relieved', '😮‍💨 Relieved'),
            ('Neutral', '😐 Neutral'),
            ('Confident', '😎 Confident'),
            ('Discouraged', '😔 Discouraged')
        ],
        validators=[DataRequired(message="Please select your emotion")]
    )
    
    emotion_intensity_after = IntegerField(
        'Emotion Intensity (1-10)',
        validators=[
            DataRequired(message="Rate your emotion intensity"),
            NumberRange(min=1, max=10)
        ]
    )
    
    # Screenshot
    screenshot_after = FileField(
        'Upload Chart Screenshot (After)',
        validators=[
            FileAllowed(['png', 'jpg', 'jpeg', 'gif', 'webp', 'heic'], 'Images only!')
        ]
    )
    
    submit = SubmitField('Complete Review')
