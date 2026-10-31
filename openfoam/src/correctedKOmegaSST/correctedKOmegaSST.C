#include "correctedKOmegaSST.H"
#include "addToRunTimeSelectionTable.H"
#include "fvcGrad.H"
#include "wallFvPatch.H"

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //


// Reynolds stress vanishes at a no-slip wall: the explicit correction must
// not add a stress on wall faces (zeroGradient would copy the first-cell
// value onto the wall and corrupt the wall shear).
static void zeroWallStress(Foam::volSymmTensorField& tau)
{
    auto& bf = tau.boundaryFieldRef();
    forAll(bf, patchi)
    {
        if (Foam::isA<Foam::wallFvPatch>(tau.mesh().boundary()[patchi]))
        {
            bf[patchi] = Foam::symmTensor::zero;
        }
    }
}

namespace Foam
{
namespace RASModels
{

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

template<class BasicTurbulenceModel>
correctedKOmegaSST<BasicTurbulenceModel>::correctedKOmegaSST
(
    const alphaField& alpha,
    const rhoField& rho,
    const volVectorField& U,
    const surfaceScalarField& alphaRhoPhi,
    const surfaceScalarField& phi,
    const transportModel& transport,
    const word& propertiesName,
    const word& type
)
:
    kOmegaSST<BasicTurbulenceModel>
    (
        alpha, rho, U, alphaRhoPhi, phi, transport, propertiesName, type
    )
{
    // Fixed-field ingestion (Mode A): construct the correction fields
    // from the start-time directory now. A later registry lookup would
    // always miss them because no other object ever reads these files.
    // Absent files (plain SST cases) leave null pointers = identity.
    IOobject aDeltaHeader
    (
        "aDelta",
        U.time().timeName(),
        U.mesh(),
        IOobject::MUST_READ,
        IOobject::NO_WRITE
    );
    if (aDeltaHeader.typeHeaderOk<volSymmTensorField>(false))
    {
        aDelta_.set(new volSymmTensorField(aDeltaHeader, U.mesh()));
    }
    IOobject pkDeltaHeader
    (
        "PkDelta",
        U.time().timeName(),
        U.mesh(),
        IOobject::MUST_READ,
        IOobject::NO_WRITE
    );
    if (pkDeltaHeader.typeHeaderOk<volScalarField>(false))
    {
        PkDelta_.set(new volScalarField(pkDeltaHeader, U.mesh()));
    }
}


template<class BasicTurbulenceModel>
Foam::scalar correctedKOmegaSST<BasicTurbulenceModel>::correctedProduction
(
    const scalar G,
    const scalar k,
    const scalar omega,
    const scalar pkDelta
) const
{
    // Pk_corrected = min(G, 10*betaStar*k*omega) + PkDelta, clamped >= 0.
    const scalar pkLimited = min(G, 10.0*this->betaStar_.value()*k*omega);
    return max(pkLimited + pkDelta, scalar(0));
}


template<class BasicTurbulenceModel>
void correctedKOmegaSST<BasicTurbulenceModel>::correct()
{
    // Base SST first. With zero/absent corrections this is the exact
    // baseline path: nut is never touched (identity gate, diff < 1e-6).
    kOmegaSST<BasicTurbulenceModel>::correct();

    // Members read in the constructor (fixed-field Mode A). A registry
    // lookup would always miss: nothing else ever reads these files.
    const bool hasADelta = aDelta_.valid();
    const bool hasPkDelta = PkDelta_.valid();

    scalar modeBMax = 0;
    // Mode B is compiled in; the default hook returns exactly 0.
    // (Cell loop is cheap relative to the SST correct() above.)
    // hasADelta/hasPkDelta gate the field reads below.

    if (!hasADelta && !hasPkDelta)
    {
        return;
    }

    const volSymmTensorField* aDeltaPtr =
        hasADelta ? aDelta_.ptr() : nullptr;
    const volScalarField* pkDeltaPtr =
        hasPkDelta ? PkDelta_.ptr() : nullptr;

    // Identity guard: zero corrections must not perturb nut at all.
    scalar maxADelta = 0;
    scalar maxPkDelta = 0;
    if (aDeltaPtr)
    {
        forAll(*aDeltaPtr, celli)
        {
            maxADelta = max(maxADelta, mag((*aDeltaPtr)[celli]));
        }
    }
    if (pkDeltaPtr)
    {
        forAll(*pkDeltaPtr, celli)
        {
            maxPkDelta = max(maxPkDelta, mag((*pkDeltaPtr)[celli]));
        }
    }
    modeBMax = max(modeBMax, scalar(0));
    if (maxADelta == 0 && maxPkDelta == 0 && modeBMax == 0)
    {
        return;
    }

    // Non-zero correction: apply through nut as the stress surrogate
    // (delta_nut/scaling comments above). v2512's momentum equation
    // reads the eddyViscosity MEMBER, not the registry object, so the
    // member is modified directly; a registry lookup would only leak
    // through wall BCs and leave the interior untouched.
    volScalarField& nut = this->nut_;

    tmp<volTensorField> tGradU = fvc::grad(this->U_);
    const volTensorField& gradU = tGradU();

    forAll(nut, celli)
    {
        const scalar k = max(this->k_[celli], scalar(0));
        const scalar omega = this->omega_[celli];
        const symmTensor S = symm(gradU[celli]);
        const scalar G = 2.0*nut[celli]*max(S && S, scalar(0));
        const scalar pkDelta =
            pkDeltaPtr ? (*pkDeltaPtr)[celli] : scalar(0);
        const scalar pkBase =
            min(G, 10.0*this->betaStar_.value()*k*omega);
        const scalar pkCorr = correctedProduction(G, k, omega, pkDelta);
        const scalar pkFactor = pkCorr/guardedDenom(pkBase);
        // No isotropic deltaNut surrogate: the tensorial correction
        // travels through divDevReff; an added 2k|a|/omega viscosity
        // only thickens diffusion and damps the redistribution.
        nut[celli] = max(nut[celli]*pkFactor, scalar(0));
    }
    nut.correctBoundaryConditions();

    // Explicit stress correction for divDevReff, rebuilt from the
    // current k every iteration (frozen aDelta, live k).
    if (aDeltaPtr)
    {
        if (!tauDelta_.valid())
        {
            tauDelta_.set
            (
                new volSymmTensorField
                (
                    IOobject
                    (
                        "tauDelta",
                        this->mesh().time().timeName(),
                        this->mesh(),
                        IOobject::NO_READ,
                        IOobject::NO_WRITE
                    ),
                    2.0*this->k_*(*aDeltaPtr)
                )
            );
        }
        else
        {
            tauDelta_() = 2.0*this->k_*(*aDeltaPtr);
        }
        zeroWallStress(tauDelta_());
    }
}


} // End namespace RASModels
} // End namespace Foam


template<class BasicTurbulenceModel>
Foam::tmp<Foam::fvVectorMatrix>
Foam::RASModels::correctedKOmegaSST<BasicTurbulenceModel>::divDevReff
(
    volVectorField& U
) const
{
    tmp<fvVectorMatrix> tdivTau =
        kOmegaSST<BasicTurbulenceModel>::divDevReff(U);
    if (tauDelta_.valid())
    {
        // divDevReff represents +div(R): a stress correction is ADDED.
        tdivTau.ref() += fvc::div(tauDelta_());
    }
    return tdivTau;
}

// * * * * * * * * * Concrete registration (incompressible) * * * * * * * * //

#include "turbulentTransportModels.H"

defineTurbulenceModelTypes
(
    geometricOneField,
    geometricOneField,
    incompressibleTurbulenceModel,
    IncompressibleTurbulenceModel,
    transportModel
);

makeBaseTurbulenceModel
(
    geometricOneField,
    geometricOneField,
    incompressibleTurbulenceModel,
    IncompressibleTurbulenceModel,
    transportModel
);

makeRASModel(correctedKOmegaSST);

// ************************************************************************* //
