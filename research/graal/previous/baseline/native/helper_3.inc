private IntegerStamp(int bits, long lowerBound, long upperBound, long mustBeSet, long mayBeSet, boolean canBeZero) {
        super(bits, OPS);

        this.lowerBound = lowerBound;
        this.upperBound = upperBound;
        this.mustBeSet = mustBeSet;
        this.mayBeSet = mayBeSet;

        // use ctor param because canBeZero is not set yet
        this.canBeZero = contains(0, canBeZero);
        assert checkInvariants();
    }
