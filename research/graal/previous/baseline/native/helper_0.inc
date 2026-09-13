private IntegerStamp(int bits, boolean empty) {
        super(bits, OPS);
        if (empty) {
            this.lowerBound = CodeUtil.maxValue(bits);
            this.upperBound = CodeUtil.minValue(bits);
            this.mustBeSet = CodeUtil.mask(bits);
            this.mayBeSet = 0;
            this.canBeZero = false;
        } else {
            this.lowerBound = CodeUtil.minValue(bits);
            this.upperBound = CodeUtil.maxValue(bits);
            this.mustBeSet = 0;
            this.mayBeSet = CodeUtil.mask(bits);
            this.canBeZero = true;
        }
    }
