private boolean checkInvariants() {
        final int allowedBitsMask = 1 | 8 | 16 | 32 | 64;
        assert (getBits() & allowedBitsMask) == getBits() && CodeUtil.isPowerOf2(getBits()) : "unexpected bit size: " + getBits();
        assert lowerBound >= CodeUtil.minValue(getBits()) : this;
        assert upperBound <= CodeUtil.maxValue(getBits()) : this;
        assert (mustBeSet & CodeUtil.mask(getBits())) == mustBeSet : this;
        assert (mayBeSet & CodeUtil.mask(getBits())) == mayBeSet : this;
        // Check for valid masks or the empty encoding
        assert (mustBeSet & ~mayBeSet) == 0 || (mayBeSet == 0 && mustBeSet == CodeUtil.mask(getBits())) : String.format("must: %016x may: %016x", mustBeSet, mayBeSet);
        assert !this.canBeZero || contains(0) : " Stamp " + this + " either has canBeZero set to false or needs to contain 0";
        assert !isEmpty() : String.format("unexpected empty stamp: %s %s %s %s %s %s", lowerBound, upperBound, mustBeSet, mayBeSet, canBeZero, this);
        assert contains(upperBound) : String.format("%s must contain its upper bound", this);
        assert contains(lowerBound) : String.format("%s must contain its lower bound", this);
        return true;
    }
