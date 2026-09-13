private IntegerStamp(int bits, long lowerBound, long upperBound) {
        super(bits, OPS);
        int sameBitCount = Long.numberOfLeadingZeros(lowerBound ^ upperBound);
        long sameBitMask = -1L >>> sameBitCount;
        long defaultMask = CodeUtil.mask(bits);

        this.lowerBound = lowerBound;
        this.upperBound = upperBound;
        this.mustBeSet = defaultMask & (lowerBound & ~sameBitMask);
        this.mayBeSet = defaultMask & (lowerBound | sameBitMask);

        this.canBeZero = contains(0, true);
        assert checkInvariants();
    }
