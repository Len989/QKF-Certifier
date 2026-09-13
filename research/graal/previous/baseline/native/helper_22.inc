public boolean isUnrestricted() {
        return lowerBound == CodeUtil.minValue(getBits()) && upperBound == CodeUtil.maxValue(getBits()) && mustBeSet == 0 && mayBeSet == CodeUtil.mask(getBits()) && canBeZero;
    }
